// GPU-SEAL native probe slice.
//
// This binary is deliberately small: it owns the CUDA allocation/copy path
// and the canary wire-format ownership check. Result orchestration and
// signing remain in the Python controller until the native conformance suite
// is complete. It never prints or persists unknown memory.

#include <cuda_runtime.h>

#include <algorithm>
#include <array>
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
#include <vector>

namespace {

constexpr std::size_t kCanarySize = 128;
constexpr std::size_t kHeaderSize = 96;
constexpr std::size_t kKeySize = 32;
constexpr std::size_t kNonceSize = 32;
constexpr std::size_t kMacSize = 32;
constexpr std::size_t kMaxAllocation = 4ULL * 1024ULL * 1024ULL * 1024ULL;
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

void run_direct(std::size_t size, std::size_t cycles, std::size_t stride) {
    if (size == 0 || size > kMaxAllocation || stride < kCanarySize) {
        throw std::invalid_argument("invalid run limits");
    }
    std::array<std::uint8_t, kKeySize> key{};
    std::array<std::uint8_t, 16> experiment{};
    fill_random(key.data(), key.size());
    fill_random(experiment.data(), experiment.size());

    std::size_t total_exact = 0;
    for (std::size_t cycle = 0; cycle < cycles; ++cycle) {
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
        std::size_t exact = 0;
        for (std::size_t i = 0; i < canaries.size(); ++i) {
            const auto* candidate = observed.data() + i * stride;
            if (std::memcmp(candidate, canaries[i].blob.data(), kCanarySize) == 0 &&
                authenticate(key, experiment, canaries[i].blob)) {
                ++exact;
            }
        }
        total_exact += exact;
    }
    std::cout << "mode=driver_direct\n"
              << "cycles=" << cycles << "\n"
              << "canary_exact_matches=" << total_exact << "\n"
              << "raw_unknown_memory_retained=false\n"
              << "unknown_memory_rendered=false\n"
              << "canary_only_search=true\n";
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
        } else if (args[0] == "--run") {
            if (std::find(args.begin(), args.end(), "--local-only") == args.end()) {
                throw std::invalid_argument("--run requires --local-only; provider use is blocked");
            }
            const auto size_mib = std::stoull(argument(args, "--size-mib"));
            const auto cycles = std::stoull(argument(args, "--cycles"));
            const auto stride_mib = std::stoull(argument(args, "--stride-mib"));
            run_direct(size_mib * 1024ULL * 1024ULL, cycles,
                       stride_mib * 1024ULL * 1024ULL);
        } else {
            throw std::invalid_argument("unknown command");
        }
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "gpu-seal-native: " << error.what() << "\n";
        return 2;
    }
}
