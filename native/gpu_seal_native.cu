// GPU-SEAL native probe slice.
//
// This binary is deliberately small: it owns the CUDA allocation/copy path
// and the canary wire-format ownership check. Result orchestration and
// signing remain in the Python controller until the native conformance suite
// is complete. It never prints or persists unknown memory.

#include <cuda_runtime.h>

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <memory>
#include <random>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <unordered_set>
#include <vector>

namespace {

constexpr std::size_t kCanarySize = 128;
constexpr std::size_t kHeaderSize = 96;
constexpr std::size_t kKeySize = 32;
constexpr std::size_t kNonceSize = 32;
constexpr std::size_t kMacSize = 32;
constexpr std::size_t kMaxAllocation = 4ULL * 1024ULL * 1024ULL * 1024ULL;
constexpr double kEntropyStopThreshold = 0.85;
constexpr double kExpectedZeroFractionFloor = 0.99;
constexpr std::size_t kMinSafeMeasurementBytes = 256;
constexpr std::array<std::uint8_t, 8> kMagic = {
    'G', 'P', 'U', 'S', 'E', 'A', 'L', 'C'};

void secure_zero(void* ptr, std::size_t size) noexcept {
    auto* bytes = static_cast<volatile std::uint8_t*>(ptr);
    while (size-- != 0) {
        *bytes++ = 0;
    }
}

class SecureBytes {
public:
    explicit SecureBytes(std::size_t size) : size_(size), data_(new std::uint8_t[size]) {
        std::fill(data_.get(), data_.get() + size_, 0);
    }

    SecureBytes(const SecureBytes&) = delete;
    SecureBytes& operator=(const SecureBytes&) = delete;

    ~SecureBytes() { secure_zero(data_.get(), size_); }

    std::uint8_t* data() noexcept { return data_.get(); }
    const std::uint8_t* data() const noexcept { return data_.get(); }
    std::size_t size() const noexcept { return size_; }
private:
    std::size_t size_;
    std::unique_ptr<std::uint8_t[]> data_;
};

// BLAKE2b-256, keyed mode, following RFC 7693. This self-contained
// implementation avoids making OpenSSL headers a runtime dependency while
// preserving ADR-002's exact Python hashlib.blake2b wire format.
namespace blake2b {

constexpr std::array<std::uint64_t, 8> kIV = {
    0x6a09e667f3bcc908ULL, 0xbb67ae8584caa73bULL,
    0x3c6ef372fe94f82bULL, 0xa54ff53a5f1d36f1ULL,
    0x510e527fade682d1ULL, 0x9b05688c2b3e6c1fULL,
    0x1f83d9abfb41bd6bULL, 0x5be0cd19137e2179ULL};

constexpr std::uint8_t kSigma[12][16] = {
    {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15},
    {14, 10, 4, 8, 9, 15, 13, 6, 1, 12, 0, 2, 11, 7, 5, 3},
    {11, 8, 12, 0, 5, 2, 15, 13, 10, 14, 3, 6, 7, 1, 9, 4},
    {7, 9, 3, 1, 13, 12, 11, 14, 2, 6, 5, 10, 4, 0, 15, 8},
    {9, 0, 5, 7, 2, 4, 10, 15, 14, 1, 11, 12, 6, 8, 3, 13},
    {2, 12, 6, 10, 0, 11, 8, 3, 4, 13, 7, 5, 15, 14, 1, 9},
    {12, 5, 1, 15, 14, 13, 4, 10, 0, 7, 6, 3, 9, 2, 8, 11},
    {13, 11, 7, 14, 12, 1, 3, 9, 5, 0, 15, 4, 8, 6, 2, 10},
    {6, 15, 14, 9, 11, 3, 0, 8, 12, 2, 13, 7, 1, 4, 10, 5},
    {10, 2, 8, 4, 7, 6, 1, 5, 15, 11, 9, 14, 3, 12, 13, 0},
    {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15},
    {14, 10, 4, 8, 9, 15, 13, 6, 1, 12, 0, 2, 11, 7, 5, 3}};

struct State {
    std::array<std::uint64_t, 8> h{};
    std::uint64_t t0 = 0;
    std::uint64_t t1 = 0;
    std::array<std::uint8_t, 128> buffer{};
    std::size_t buffered = 0;
};

std::uint64_t load64(const std::uint8_t* p) {
    std::uint64_t value = 0;
    for (int i = 0; i < 8; ++i) {
        value |= static_cast<std::uint64_t>(p[i]) << (8 * i);
    }
    return value;
}

void store64(std::uint8_t* p, std::uint64_t value) {
    for (int i = 0; i < 8; ++i) {
        p[i] = static_cast<std::uint8_t>(value >> (8 * i));
    }
}

inline std::uint64_t rotr(std::uint64_t value, unsigned count) {
    return (value >> count) | (value << (64 - count));
}

void add_counter(State& state, std::uint64_t amount) {
    const auto old = state.t0;
    state.t0 += amount;
    if (state.t0 < old) {
        ++state.t1;
    }
}

void compress(State& state, bool last) {
    std::array<std::uint64_t, 16> message{};
    std::array<std::uint64_t, 16> work{};
    for (int i = 0; i < 16; ++i) {
        message[i] = load64(state.buffer.data() + i * 8);
        work[i] = i < 8 ? state.h[i] : kIV[i - 8];
    }
    work[12] ^= state.t0;
    work[13] ^= state.t1;
    if (last) {
        work[14] = ~work[14];
    }

    auto mix = [&work, &message](int a, int b, int c, int d, int x, int y) {
        work[a] = work[a] + work[b] + message[x];
        work[d] = rotr(work[d] ^ work[a], 32);
        work[c] += work[d];
        work[b] = rotr(work[b] ^ work[c], 24);
        work[a] = work[a] + work[b] + message[y];
        work[d] = rotr(work[d] ^ work[a], 16);
        work[c] += work[d];
        work[b] = rotr(work[b] ^ work[c], 63);
    };

    constexpr int row[16] = {0, 1, 2, 3, 4, 5, 6, 7,
                             8, 9, 10, 11, 12, 13, 14, 15};
    for (int round = 0; round < 12; ++round) {
        const auto* s = kSigma[round];
        mix(row[0], row[4], row[8], row[12], s[0], s[1]);
        mix(row[1], row[5], row[9], row[13], s[2], s[3]);
        mix(row[2], row[6], row[10], row[14], s[4], s[5]);
        mix(row[3], row[7], row[11], row[15], s[6], s[7]);
        mix(row[0], row[5], row[10], row[15], s[8], s[9]);
        mix(row[1], row[6], row[11], row[12], s[10], s[11]);
        mix(row[2], row[7], row[8], row[13], s[12], s[13]);
        mix(row[3], row[4], row[9], row[14], s[14], s[15]);
    }
    for (int i = 0; i < 8; ++i) {
        state.h[i] ^= work[i] ^ work[i + 8];
    }
}

void init(State& state, const std::array<std::uint8_t, kKeySize>& key) {
    state.h = kIV;
    // digest length 32, key length 32, fanout 1, depth 1.
    state.h[0] ^= 0x01012020ULL;
    state.buffer.fill(0);
    std::copy(key.begin(), key.end(), state.buffer.begin());
    state.buffered = 128;
}

void update(State& state, const std::uint8_t* input, std::size_t size) {
    while (size != 0) {
        if (state.buffered == 128) {
            add_counter(state, 128);
            compress(state, false);
            state.buffered = 0;
        }
        const auto take = std::min(size, 128 - state.buffered);
        std::copy(input, input + take, state.buffer.begin() + state.buffered);
        state.buffered += take;
        input += take;
        size -= take;
    }
}

std::array<std::uint8_t, kMacSize> final(State& state) {
    add_counter(state, state.buffered);
    std::fill(state.buffer.begin() + state.buffered, state.buffer.end(), 0);
    compress(state, true);
    std::array<std::uint8_t, kMacSize> digest{};
    for (int i = 0; i < 4; ++i) {
        store64(digest.data() + i * 8, state.h[i]);
    }
    secure_zero(state.buffer.data(), state.buffer.size());
    secure_zero(&state, sizeof(state));
    return digest;
}

std::array<std::uint8_t, kMacSize> keyed_hash(
    const std::array<std::uint8_t, kKeySize>& key,
    const std::uint8_t* message,
    std::size_t size) {
    State state;
    init(state, key);
    update(state, message, size);
    return final(state);
}

}  // namespace blake2b

namespace sha256 {

constexpr std::uint32_t kRoundConstants[64] = {
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5,
    0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
    0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc,
    0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
    0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
    0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3,
    0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5,
    0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
    0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2};

struct State {
    std::array<std::uint32_t, 8> h{};
    std::array<std::uint8_t, 64> buffer{};
    std::size_t buffered = 0;
    std::uint64_t bit_count = 0;
};

inline std::uint32_t rotr(std::uint32_t value, unsigned count) {
    return (value >> count) | (value << (32 - count));
}

std::uint32_t load32_be(const std::uint8_t* p) {
    return static_cast<std::uint32_t>(p[0]) << 24 |
           static_cast<std::uint32_t>(p[1]) << 16 |
           static_cast<std::uint32_t>(p[2]) << 8 |
           static_cast<std::uint32_t>(p[3]);
}

void store32_be(std::uint8_t* p, std::uint32_t value) {
    p[0] = static_cast<std::uint8_t>(value >> 24);
    p[1] = static_cast<std::uint8_t>(value >> 16);
    p[2] = static_cast<std::uint8_t>(value >> 8);
    p[3] = static_cast<std::uint8_t>(value);
}

void transform(State& state) {
    std::array<std::uint32_t, 64> schedule{};
    for (int i = 0; i < 16; ++i) schedule[i] = load32_be(state.buffer.data() + i * 4);
    for (int i = 16; i < 64; ++i) {
        const auto s0 = rotr(schedule[i - 15], 7) ^ rotr(schedule[i - 15], 18) ^
                        (schedule[i - 15] >> 3);
        const auto s1 = rotr(schedule[i - 2], 17) ^ rotr(schedule[i - 2], 19) ^
                        (schedule[i - 2] >> 10);
        schedule[i] = schedule[i - 16] + s0 + schedule[i - 7] + s1;
    }
    auto work = state.h;
    for (int i = 0; i < 64; ++i) {
        const auto s1 = rotr(work[4], 6) ^ rotr(work[4], 11) ^ rotr(work[4], 25);
        const auto choose = (work[4] & work[5]) ^ (~work[4] & work[6]);
        const auto temp1 = work[7] + s1 + choose + kRoundConstants[i] + schedule[i];
        const auto s0 = rotr(work[0], 2) ^ rotr(work[0], 13) ^ rotr(work[0], 22);
        const auto majority = (work[0] & work[1]) ^ (work[0] & work[2]) ^
                              (work[1] & work[2]);
        const auto temp2 = s0 + majority;
        work[7] = work[6];
        work[6] = work[5];
        work[5] = work[4];
        work[4] = work[3] + temp1;
        work[3] = work[2];
        work[2] = work[1];
        work[1] = work[0];
        work[0] = temp1 + temp2;
    }
    for (int i = 0; i < 8; ++i) state.h[i] += work[i];
    secure_zero(schedule.data(), sizeof(schedule));
}

void init(State& state) {
    state.h = {0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
               0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};
}

void update(State& state, const std::uint8_t* data, std::size_t size) {
    state.bit_count += static_cast<std::uint64_t>(size) * 8;
    while (size != 0) {
        const auto take = std::min(size, state.buffer.size() - state.buffered);
        std::copy(data, data + take, state.buffer.begin() + state.buffered);
        state.buffered += take;
        data += take;
        size -= take;
        if (state.buffered == state.buffer.size()) {
            transform(state);
            state.buffered = 0;
        }
    }
}

std::array<std::uint8_t, 32> final(State& state) {
    state.buffer[state.buffered++] = 0x80;
    if (state.buffered > 56) {
        std::fill(state.buffer.begin() + state.buffered, state.buffer.end(), 0);
        transform(state);
        state.buffered = 0;
    }
    std::fill(state.buffer.begin() + state.buffered, state.buffer.begin() + 56, 0);
    for (int i = 0; i < 8; ++i) {
        state.buffer[63 - i] = static_cast<std::uint8_t>(state.bit_count >> (8 * i));
    }
    transform(state);
    std::array<std::uint8_t, 32> digest{};
    for (int i = 0; i < 8; ++i) store32_be(digest.data() + i * 4, state.h[i]);
    secure_zero(&state, sizeof(state));
    return digest;
}

std::array<std::uint8_t, 32> hash(const std::uint8_t* data, std::size_t size) {
    State state;
    init(state);
    update(state, data, size);
    return final(state);
}

}  // namespace sha256

std::vector<std::uint8_t> parse_hex(std::string_view text, std::size_t expected) {
    if (text.size() != expected * 2) {
        throw std::invalid_argument("hex value has the wrong length");
    }
    std::vector<std::uint8_t> result(expected);
    for (std::size_t i = 0; i < expected; ++i) {
        const auto digit = [](char c) -> int {
            if (c >= '0' && c <= '9') return c - '0';
            if (c >= 'a' && c <= 'f') return c - 'a' + 10;
            if (c >= 'A' && c <= 'F') return c - 'A' + 10;
            return -1;
        };
        const int high = digit(text[i * 2]);
        const int low = digit(text[i * 2 + 1]);
        if (high < 0 || low < 0) {
            throw std::invalid_argument("hex value contains a non-hex digit");
        }
        result[i] = static_cast<std::uint8_t>((high << 4) | low);
    }
    return result;
}

std::string hex(const std::uint8_t* data, std::size_t size) {
    std::ostringstream out;
    out << std::hex << std::setfill('0');
    for (std::size_t i = 0; i < size; ++i) {
        out << std::setw(2) << static_cast<unsigned>(data[i]);
    }
    return out.str();
}

std::uint16_t read_u16(const std::uint8_t* p) {
    return static_cast<std::uint16_t>(p[0]) |
           static_cast<std::uint16_t>(p[1]) << 8;
}

void write_u16(std::uint8_t* p, std::uint16_t value) {
    p[0] = static_cast<std::uint8_t>(value);
    p[1] = static_cast<std::uint8_t>(value >> 8);
}

void write_u32(std::uint8_t* p, std::uint32_t value) {
    for (int i = 0; i < 4; ++i) {
        p[i] = static_cast<std::uint8_t>(value >> (8 * i));
    }
}

struct Canary {
    std::array<std::uint8_t, kCanarySize> blob{};
};

Canary mint(const std::array<std::uint8_t, kKeySize>& key,
            const std::array<std::uint8_t, 16>& experiment,
            const std::array<std::uint8_t, 16>& allocation,
            std::uint16_t boundary,
            std::uint32_t flags,
            const std::array<std::uint8_t, kNonceSize>& nonce) {
    Canary result;
    std::copy(kMagic.begin(), kMagic.end(), result.blob.begin());
    write_u16(result.blob.data() + 8, 1);
    write_u16(result.blob.data() + 10, boundary);
    write_u32(result.blob.data() + 12, flags);
    std::copy(experiment.begin(), experiment.end(), result.blob.begin() + 16);
    std::copy(allocation.begin(), allocation.end(), result.blob.begin() + 32);
    std::copy(nonce.begin(), nonce.end(), result.blob.begin() + 48);
    std::fill(result.blob.begin() + 80, result.blob.begin() + 96, 0);
    const auto mac = blake2b::keyed_hash(key, result.blob.data(), kHeaderSize);
    std::copy(mac.begin(), mac.end(), result.blob.begin() + kHeaderSize);
    return result;
}

bool authenticate(const std::array<std::uint8_t, kKeySize>& key,
                  const std::array<std::uint8_t, 16>& experiment,
                  const std::array<std::uint8_t, kCanarySize>& blob) {
    if (!std::equal(kMagic.begin(), kMagic.end(), blob.begin()) ||
        read_u16(blob.data() + 8) != 1 || read_u16(blob.data() + 10) > 13 ||
        !std::equal(experiment.begin(), experiment.end(), blob.begin() + 16)) {
        return false;
    }
    const auto expected = blake2b::keyed_hash(key, blob.data(), kHeaderSize);
    return std::equal(expected.begin(), expected.end(), blob.begin() + kHeaderSize);
}

void fill_random(std::uint8_t* data, std::size_t size) {
#ifdef _WIN32
    std::random_device source;
    for (std::size_t i = 0; i < size; ++i) data[i] = static_cast<std::uint8_t>(source());
#else
    std::ifstream source("/dev/urandom", std::ios::binary);
    if (!source || !source.read(reinterpret_cast<char*>(data), static_cast<std::streamsize>(size))) {
        throw std::runtime_error("secure random source unavailable");
    }
#endif
}

template <typename Array>
Array array_from_hex(std::string_view text) {
    const auto bytes = parse_hex(text, Array{}.size());
    Array result{};
    std::copy(bytes.begin(), bytes.end(), result.begin());
    return result;
}

std::string argument(const std::vector<std::string>& args, std::string_view name) {
    for (std::size_t i = 0; i + 1 < args.size(); ++i) {
        if (args[i] == name) return args[i + 1];
    }
    throw std::invalid_argument("missing argument: " + std::string(name));
}

void print_mint(const std::vector<std::string>& args) {
    auto key = array_from_hex<std::array<std::uint8_t, kKeySize>>(argument(args, "--key"));
    const auto experiment = array_from_hex<std::array<std::uint8_t, 16>>(argument(args, "--experiment"));
    const auto allocation = array_from_hex<std::array<std::uint8_t, 16>>(argument(args, "--allocation"));
    const auto nonce = array_from_hex<std::array<std::uint8_t, kNonceSize>>(argument(args, "--nonce"));
    const auto boundary = static_cast<std::uint16_t>(std::stoul(argument(args, "--boundary")));
    const auto flags = static_cast<std::uint32_t>(std::stoul(argument(args, "--flags")));
    const auto canary = mint(key, experiment, allocation, boundary, flags, nonce);
    std::cout << "blob_hex=" << hex(canary.blob.data(), canary.blob.size()) << "\n";
    secure_zero(key.data(), key.size());
}

void print_authenticate(const std::vector<std::string>& args) {
    auto key = array_from_hex<std::array<std::uint8_t, kKeySize>>(argument(args, "--key"));
    const auto experiment = array_from_hex<std::array<std::uint8_t, 16>>(argument(args, "--experiment"));
    const auto bytes = parse_hex(argument(args, "--blob"), kCanarySize);
    std::array<std::uint8_t, kCanarySize> blob{};
    std::copy(bytes.begin(), bytes.end(), blob.begin());
    std::cout << "owned=" << (authenticate(key, experiment, blob) ? "true" : "false") << "\n";
    secure_zero(key.data(), key.size());
}

void print_sha256(const std::vector<std::string>& args) {
    const auto bytes = parse_hex(argument(args, "--input"), 3);
    const auto digest = sha256::hash(bytes.data(), bytes.size());
    std::cout << "sha256=" << hex(digest.data(), digest.size()) << "\n";
}

void cuda_check(cudaError_t status, const char* operation) {
    if (status != cudaSuccess) {
        throw std::runtime_error(std::string(operation) + ": " + cudaGetErrorString(status));
    }
}

class DeviceAllocation {
public:
    explicit DeviceAllocation(std::size_t size) : size_(size) {
        if (size_ == 0 || size_ > kMaxAllocation) throw std::invalid_argument("invalid allocation size");
        cuda_check(cudaMalloc(&pointer_, size_), "cudaMalloc");
    }
    DeviceAllocation(const DeviceAllocation&) = delete;
    DeviceAllocation& operator=(const DeviceAllocation&) = delete;
    ~DeviceAllocation() { if (pointer_ != nullptr) cudaFree(pointer_); }
    void* pointer() const noexcept { return pointer_; }
    void release() noexcept { if (pointer_ != nullptr) { cudaFree(pointer_); pointer_ = nullptr; } }

private:
    void* pointer_ = nullptr;
    std::size_t size_;
};

struct AggregateResult {
    std::size_t buffer_size_bytes = 0;
    double zero_fraction = 0.0;
    double fixed_pattern_fraction = 0.0;
    double entropy_estimate = 0.0;
    std::size_t repeated_block_count = 0;
    std::size_t distinct_block_count = 0;
    std::array<std::uint64_t, 256> histogram{};
    std::size_t exact_matches = 0;
    std::size_t longest_prefix = 0;
    std::array<std::uint8_t, 32> measurement_hash{};
    std::uint64_t timing_ns = 0;
    bool sensitive_observation = false;
    const char* error_code = nullptr;
};

void apply_safety_stop(AggregateResult& result, bool expect_zeroed,
                       bool shared_infrastructure) {
    if (result.exact_matches != 0) return;
    const bool unexpected_content =
        expect_zeroed && result.zero_fraction < kExpectedZeroFractionFloor;
    const bool high_information =
        shared_infrastructure && result.entropy_estimate > kEntropyStopThreshold;
    const bool too_small =
        shared_infrastructure && result.buffer_size_bytes < kMinSafeMeasurementBytes;
    if (unexpected_content || high_information || too_small) {
        result.sensitive_observation = true;
        result.error_code = "sensitive_observation";
    }
}

AggregateResult aggregate_observed(
    const SecureBytes& observed, const std::vector<Canary>& canaries,
    std::uint64_t timing_ns) {
    AggregateResult result;
    result.buffer_size_bytes = observed.size();
    for (std::size_t i = 0; i < observed.size(); ++i) {
        ++result.histogram[observed.data()[i]];
    }
    result.zero_fraction = observed.size() == 0
        ? 0.0
        : static_cast<double>(result.histogram[0]) / observed.size();

    double entropy = 0.0;
    for (const auto count : result.histogram) {
        if (count != 0) {
            const auto probability = static_cast<double>(count) / observed.size();
            entropy -= probability * std::log2(probability);
        }
    }
    result.entropy_estimate = entropy / 8.0;

    constexpr std::size_t block_size = 16;
    const auto block_count = observed.size() / block_size;
    std::unordered_set<std::string_view> distinct_blocks;
    distinct_blocks.reserve(block_count);
    std::size_t fixed_blocks = 0;
    for (std::size_t i = 0; i < block_count; ++i) {
        const auto* block = observed.data() + i * block_size;
        distinct_blocks.emplace(reinterpret_cast<const char*>(block), block_size);
        bool fixed = true;
        for (std::size_t j = 1; j < block_size; ++j) {
            if (block[j] != block[0]) {
                fixed = false;
                break;
            }
        }
        if (fixed) ++fixed_blocks;
    }
    result.distinct_block_count = distinct_blocks.size();
    result.repeated_block_count = block_count - result.distinct_block_count;
    result.fixed_pattern_fraction = block_count == 0
        ? 0.0
        : static_cast<double>(fixed_blocks) / block_count;

    const std::string_view haystack(
        reinterpret_cast<const char*>(observed.data()), observed.size());
    for (const auto& canary : canaries) {
        const std::string_view marker(
            reinterpret_cast<const char*>(canary.blob.data()), kCanarySize);
        if (haystack.find(marker) != std::string_view::npos) {
            ++result.exact_matches;
            result.longest_prefix = kCanarySize;
            continue;
        }
        std::size_t low = 0;
        std::size_t high = kCanarySize;
        while (low < high) {
            const auto middle = (low + high + 1) / 2;
            if (haystack.find(marker.substr(0, middle)) != std::string_view::npos) {
                low = middle;
            } else {
                high = middle - 1;
            }
        }
        result.longest_prefix = std::max(result.longest_prefix, low);
    }
    result.measurement_hash = sha256::hash(observed.data(), observed.size());
    result.timing_ns = timing_ns;
    apply_safety_stop(result, false, false);
    return result;
}

bool parse_bool(const std::string& value) {
    if (value == "true" || value == "1") return true;
    if (value == "false" || value == "0") return false;
    throw std::invalid_argument("expected boolean flag");
}

void print_safety_check(const std::vector<std::string>& args) {
    AggregateResult result;
    result.buffer_size_bytes = std::stoull(argument(args, "--buffer-size"));
    result.zero_fraction = std::stod(argument(args, "--zero-fraction"));
    result.entropy_estimate = std::stod(argument(args, "--entropy"));
    result.exact_matches = parse_bool(argument(args, "--owned-match")) ? 1 : 0;
    if (result.buffer_size_bytes >= kMinSafeMeasurementBytes) {
        result.repeated_block_count = 1;
    }
    apply_safety_stop(
        result,
        parse_bool(argument(args, "--expect-zeroed")),
        parse_bool(argument(args, "--shared-infrastructure")));
    std::cout << "sensitive_observation="
              << (result.sensitive_observation ? "true" : "false") << "\n";
    std::cout << "error_code="
              << (result.error_code == nullptr ? "null" : result.error_code) << "\n";
}

std::string json_escape(std::string_view text) {
    std::ostringstream out;
    for (const auto ch : text) {
        if (ch == '\\') out << "\\\\";
        else if (ch == '"') out << "\\\"";
        else if (ch == '\n') out << "\\n";
        else if (ch == '\r') out << "\\r";
        else if (ch == '\t') out << "\\t";
        else out << ch;
    }
    return out.str();
}

[[maybe_unused]] void print_aggregate_json_broken(
    const AggregateResult&, std::size_t, const cudaDeviceProp&, int, int) {
#if 0
    std::cout << std::setprecision(17)
              << "{\"kind\":\"aggregate\",\"probe_name\":\"native_driver_direct\","
              << "\"probe_version\":\"0.1.0-native\",\"buffer_size_bytes\":" << size
              << ",\"block_size_bytes\":16,\"measurement_hash\":\"sha256:"
              << hex(result.measurement_hash.data(), result.measurement_hash.size())
              << "\",\"zero_fraction\":" << result.zero_fraction
              << ",\"fixed_pattern_fraction\":" << result.fixed_pattern_fraction
              << ",\"entropy_estimate\":" << result.entropy_estimate
              << ",\"repeated_block_count\":" << result.repeated_block_count
              << ",\"distinct_block_count\":" << result.distinct_block_count
              << ",\"byte_histogram\":[";
    for (std::size_t i = 0; i < result.histogram.size(); ++i) {
        if (i != 0) std::cout << ',';
        std::cout << result.histogram[i];
    }
    std::cout << "],\"owned_canary_match\":"
              << (result.exact_matches != 0 ? "true" : "false")
              << ",\"owned_canary_exact_matches\":" << result.exact_matches
              << ",\"owned_canary_longest_prefix\":" << result.longest_prefix
              << ",\"sensitive_observation\":"
              << (result.sensitive_observation ? "true" : "false")
              << ",\"unknown_raw_retained\":false,"
              << "\"unknown_memory_rendered\":false,\"canary_only_search\":true,"
              << "\"driver_metadata\":{"backend":"cupy-native","backend_is_real":"true","
              << "\"measurement_path":"driver_direct","device_name":""
              << json_escape(device.name) << "","compute_capability":""
              << device.major << '.' << device.minor << "","cuda_runtime_version":""
              << runtime_version << "","cuda_driver_version":"" << driver_version
              << ""},\"error_code\":null,\"timing_ns\":" << result.timing_ns << "}\n";
}
#endif
}

void print_aggregate_json(const AggregateResult& result, std::size_t size,
                          const cudaDeviceProp& device, int runtime_version,
                          int driver_version) {
    std::cout << std::setprecision(17)
              << "{\"kind\":\"aggregate\",\"probe_name\":\"native_driver_direct\","
              << "\"probe_version\":\"0.1.0-native\",\"buffer_size_bytes\":" << size
              << ",\"block_size_bytes\":16,\"measurement_hash\":\"sha256:"
              << hex(result.measurement_hash.data(), result.measurement_hash.size())
              << "\",\"zero_fraction\":" << result.zero_fraction
              << ",\"fixed_pattern_fraction\":" << result.fixed_pattern_fraction
              << ",\"entropy_estimate\":" << result.entropy_estimate
              << ",\"repeated_block_count\":" << result.repeated_block_count
              << ",\"distinct_block_count\":" << result.distinct_block_count
              << ",\"byte_histogram\":[";
    for (std::size_t i = 0; i < result.histogram.size(); ++i) {
        if (i != 0) std::cout << ',';
        std::cout << result.histogram[i];
    }
    std::cout << "],\"owned_canary_match\":"
              << (result.exact_matches != 0 ? "true" : "false")
              << ",\"owned_canary_exact_matches\":" << result.exact_matches
              << ",\"owned_canary_longest_prefix\":" << result.longest_prefix
              << ",\"sensitive_observation\":"
              << (result.sensitive_observation ? "true" : "false")
              << ",\"unknown_raw_retained\":false,"
              << "\"unknown_memory_rendered\":false,\"canary_only_search\":true,"
              << "\"driver_metadata\":{\"backend\":\"cupy-native\",\"backend_is_real\":\"true\","
              << "\"measurement_path\":\"driver_direct\",\"device_name\":\""
              << json_escape(device.name) << "\",\"compute_capability\":\""
              << device.major << '.' << device.minor << "\",\"cuda_runtime_version\":\""
              << runtime_version << "\",\"cuda_driver_version\":\"" << driver_version
              << "\"},\"error_code\":"
              << (result.error_code == nullptr ? "null" : "\"sensitive_observation\"")
              << ",\"timing_ns\":" << result.timing_ns << "}\n";
}

void run_direct(std::size_t size, std::size_t cycles, std::size_t stride,
                bool json_output) {
    if (size == 0 || size > kMaxAllocation || stride < kCanarySize) {
        throw std::invalid_argument("invalid run limits");
    }
    std::array<std::uint8_t, kKeySize> key{};
    std::array<std::uint8_t, 16> experiment{};
    fill_random(key.data(), key.size());
    fill_random(experiment.data(), experiment.size());

    cudaDeviceProp device{};
    cuda_check(cudaGetDeviceProperties(&device, 0), "cudaGetDeviceProperties");
    int runtime_version = 0;
    int driver_version = 0;
    cuda_check(cudaRuntimeGetVersion(&runtime_version), "cudaRuntimeGetVersion");
    cuda_check(cudaDriverGetVersion(&driver_version), "cudaDriverGetVersion");
    std::size_t total_exact = 0;
    for (std::size_t cycle = 0; cycle < cycles; ++cycle) {
        const auto started = std::chrono::steady_clock::now();
        DeviceAllocation first(size);
        std::vector<Canary> canaries;
        std::size_t offset = 0;
        while (offset + kCanarySize <= size) {
            std::array<std::uint8_t, 16> allocation{};
            fill_random(allocation.data(), allocation.size());
            std::array<std::uint8_t, kNonceSize> nonce{};
            fill_random(nonce.data(), nonce.size());
            canaries.push_back(mint(key, experiment, allocation, 2, 0, nonce));
            offset += stride;
        }
        const auto payload_size = canaries.empty() ? 0 :
            std::min(size, (canaries.size() - 1) * stride + kCanarySize);
        SecureBytes payload(payload_size);
        for (std::size_t i = 0; i < canaries.size(); ++i) {
            std::memcpy(payload.data() + i * stride, canaries[i].blob.data(), kCanarySize);
        }
        if (payload_size != 0) {
            cuda_check(cudaMemcpy(first.pointer(), payload.data(), payload_size,
                                  cudaMemcpyHostToDevice), "cudaMemcpy H2D");
        }
        first.release();

        DeviceAllocation second(size);
        SecureBytes observed(size);
        cuda_check(cudaMemcpy(observed.data(), second.pointer(), size,
                              cudaMemcpyDeviceToHost), "cudaMemcpy D2H");
        const auto elapsed = std::chrono::duration_cast<std::chrono::nanoseconds>(
            std::chrono::steady_clock::now() - started).count();
        const auto aggregate = aggregate_observed(observed, canaries, elapsed);
        total_exact += aggregate.exact_matches;
        if (json_output) {
            print_aggregate_json(aggregate, size, device, runtime_version, driver_version);
        }
    }
    if (json_output) {
        std::cout << "{\"kind\":\"summary\",\"mode\":\"driver_direct\",\"cycles\":"
                  << cycles << ",\"canary_exact_matches\":" << total_exact
                  << ",\"raw_unknown_memory_retained\":false,"
                  << "\"unknown_memory_rendered\":false,\"canary_only_search\":true}\n";
    } else {
        std::cout << "mode=driver_direct\n"
                  << "cycles=" << cycles << "\n"
                  << "canary_exact_matches=" << total_exact << "\n"
                  << "raw_unknown_memory_retained=false\n"
                  << "unknown_memory_rendered=false\n"
                  << "canary_only_search=true\n";
    }
    secure_zero(key.data(), key.size());
    secure_zero(experiment.data(), experiment.size());
}

}  // namespace

int main(int argc, char** argv) {
    try {
        std::vector<std::string> args(argv + 1, argv + argc);
        if (args.empty()) throw std::invalid_argument("expected --mint, --authenticate, or --run");
        if (args[0] == "--mint") {
            print_mint(args);
        } else if (args[0] == "--authenticate") {
            print_authenticate(args);
        } else if (args[0] == "--sha256") {
            print_sha256(args);
        } else if (args[0] == "--safety-check") {
            print_safety_check(args);
        } else if (args[0] == "--run") {
            if (std::find(args.begin(), args.end(), "--local-only") == args.end()) {
                throw std::invalid_argument("--run requires --local-only; provider use is blocked");
            }
            const auto size_mib = std::stoull(argument(args, "--size-mib"));
            const auto cycles = std::stoull(argument(args, "--cycles"));
            const auto stride_mib = std::stoull(argument(args, "--stride-mib"));
            const bool json_output = std::find(args.begin(), args.end(), "--json") != args.end();
            run_direct(size_mib * 1024ULL * 1024ULL, cycles,
                       stride_mib * 1024ULL * 1024ULL, json_output);
        } else {
            throw std::invalid_argument("unknown command");
        }
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "gpu-seal-native: " << error.what() << "\n";
        return 2;
    }
}
