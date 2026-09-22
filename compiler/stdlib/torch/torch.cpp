#include <ATen/ATen.h>
#include <torch/torch.h>
#include <cstring>
#include <utility>

struct Tensor { char* __handle; };
struct ListF64 { long long size; double* data; };

static torch::Tensor& handle(Tensor t) {
    return *(torch::Tensor*)t.__handle;
}

extern "C" {

Tensor Tensor___init__(Tensor self, ListF64 data) {
    torch::Tensor t = at::from_blob(
        (void*)data.data,
        at::IntArrayRef({(int64_t)data.size}),
        at::kDouble
    ).clone();
    auto* p = new torch::Tensor(std::move(t));
    Tensor out;
    out.__handle = (char*)p;
    return out;
}

double Tensor___item(Tensor self) {
    return handle(self).item<double>();
}

double Tensor___at(Tensor self, long long i) {
    return handle(self)[i].item<double>();
}

double Tensor___sum(Tensor self) {
    return handle(self).sum().item<double>();
}

double Tensor___mean(Tensor self) {
    return handle(self).mean().item<double>();
}

double Tensor___max(Tensor self) {
    return handle(self).max().item<double>();
}

double Tensor___min(Tensor self) {
    return handle(self).min().item<double>();
}

long long Tensor___dim(Tensor self) {
    return (long long)handle(self).dim();
}

long long Tensor___numel(Tensor self) {
    return (long long)handle(self).numel();
}

ListF64 arange(double end) {
    auto r = at::arange(end, at::kDouble);
    int64_t n = r.numel();
    double* buf = new double[n];
    memcpy(buf, r.data_ptr<double>(), (size_t)n * sizeof(double));
    ListF64 out;
    out.size = n;
    out.data = buf;
    return out;
}

}