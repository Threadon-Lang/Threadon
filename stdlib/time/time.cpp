#include <chrono>
#include <ctime>
#include <thread>

extern "C" long long now() {
    return static_cast<long long>(
        std::chrono::system_clock::to_time_t(std::chrono::system_clock::now())
    );
}

extern "C" long long cpu_time() {
    return static_cast<long long>(std::clock());
}

extern "C" double diff(long long from, long long to) {
    return std::difftime(static_cast<std::time_t>(to),
                         static_cast<std::time_t>(from));
}

extern "C" double monotonic() {
    return std::chrono::duration<double>(
               std::chrono::steady_clock::now().time_since_epoch()
    ).count();
}

extern "C" long long sleep_ms(long long ms) {
    std::this_thread::sleep_for(std::chrono::milliseconds(ms));
    return ms;
}
