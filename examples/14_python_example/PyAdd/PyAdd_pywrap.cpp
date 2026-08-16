#include <Python.h>
#include <cstdlib>
#include <cstring>
extern "C" {
static bool _py_init = false;
static void ensure_init() {
    if (!_py_init) {
        Py_Initialize();
        PyRun_SimpleString("import sys; sys.path.insert(0, \"/home/joep/projects/AGI/threadon/examples/14_python_example/PyAdd\")");
        _py_init = true;
    }
}
} // extern C (init helpers stay C-linkage-free of struct ABI concerns)

struct ThList_Float64 { long long len; double* data; };
struct ThDict_String_Float64 { long long len; char** keys; double* values; };

extern "C" {
double add(double a0, double a1) {
    ensure_init();
    PyObject* args = PyTuple_New(2);
    PyObject* _pyv1 = PyFloat_FromDouble(a0);
    PyTuple_SetItem(args, 0, _pyv1);
    PyObject* _pyv2 = PyFloat_FromDouble(a1);
    PyTuple_SetItem(args, 1, _pyv2);
    PyObject* mod = PyImport_ImportModule("padd");
    if (!mod) return 0.0;
    PyObject* f = PyObject_GetAttrString(mod, "add");
    Py_DECREF(mod);
    if (!f || !PyCallable_Check(f)) { Py_XDECREF(f); return 0.0; }
    PyObject* r = PyObject_CallObject(f, args);
    Py_DECREF(f);
    Py_DECREF(args);
    if (!r) { PyErr_Clear(); return 0.0; }
    double _out3 = PyFloat_AsDouble(r);
    Py_DECREF(r);
    return _out3;
}
double scale(double a0, double a1) {
    ensure_init();
    PyObject* args = PyTuple_New(2);
    PyObject* _pyv4 = PyFloat_FromDouble(a0);
    PyTuple_SetItem(args, 0, _pyv4);
    PyObject* _pyv5 = PyFloat_FromDouble(a1);
    PyTuple_SetItem(args, 1, _pyv5);
    PyObject* mod = PyImport_ImportModule("padd");
    if (!mod) return 0.0;
    PyObject* f = PyObject_GetAttrString(mod, "scale");
    Py_DECREF(mod);
    if (!f || !PyCallable_Check(f)) { Py_XDECREF(f); return 0.0; }
    PyObject* r = PyObject_CallObject(f, args);
    Py_DECREF(f);
    Py_DECREF(args);
    if (!r) { PyErr_Clear(); return 0.0; }
    double _out6 = PyFloat_AsDouble(r);
    Py_DECREF(r);
    return _out6;
}
double mean(ThList_Float64 a0) {
    ensure_init();
    PyObject* args = PyTuple_New(1);
    PyObject* _lst8 = PyList_New(a0.len);
    for (long long _i9 = 0; _i9 < a0.len; _i9++) {
    PyObject* _it10 = PyFloat_FromDouble(a0.data[_i9]);
        PyList_SetItem(_lst8, _i9, _it10);
    }
    PyObject* _pyv7 = _lst8;
    PyTuple_SetItem(args, 0, _pyv7);
    PyObject* mod = PyImport_ImportModule("padd");
    if (!mod) return 0.0;
    PyObject* f = PyObject_GetAttrString(mod, "mean");
    Py_DECREF(mod);
    if (!f || !PyCallable_Check(f)) { Py_XDECREF(f); return 0.0; }
    PyObject* r = PyObject_CallObject(f, args);
    Py_DECREF(f);
    Py_DECREF(args);
    if (!r) { PyErr_Clear(); return 0.0; }
    double _out11 = PyFloat_AsDouble(r);
    Py_DECREF(r);
    return _out11;
}
ThList_Float64 normalize(ThList_Float64 a0) {
    ensure_init();
    PyObject* args = PyTuple_New(1);
    PyObject* _lst13 = PyList_New(a0.len);
    for (long long _i14 = 0; _i14 < a0.len; _i14++) {
    PyObject* _it15 = PyFloat_FromDouble(a0.data[_i14]);
        PyList_SetItem(_lst13, _i14, _it15);
    }
    PyObject* _pyv12 = _lst13;
    PyTuple_SetItem(args, 0, _pyv12);
    PyObject* mod = PyImport_ImportModule("padd");
    if (!mod) return ThList_Float64{0, nullptr};
    PyObject* f = PyObject_GetAttrString(mod, "normalize");
    Py_DECREF(mod);
    if (!f || !PyCallable_Check(f)) { Py_XDECREF(f); return ThList_Float64{0, nullptr}; }
    PyObject* r = PyObject_CallObject(f, args);
    Py_DECREF(f);
    Py_DECREF(args);
    if (!r) { PyErr_Clear(); return ThList_Float64{0, nullptr}; }
    ThList_Float64 out;
    Py_ssize_t _n16 = PySequence_Size(r);
    out.len = (long long)_n16;
    out.data = (double*)malloc(sizeof(double) * (size_t)_n16);
    for (Py_ssize_t _i17 = 0; _i17 < _n16; _i17++) {
        PyObject* _item18 = PySequence_GetItem(r, _i17);
    out.data[_i17] = PyFloat_AsDouble(_item18);
        Py_DECREF(_item18);
    }
    Py_DECREF(r);
    return out;
}
ThDict_String_Float64 describe(ThList_Float64 a0) {
    ensure_init();
    PyObject* args = PyTuple_New(1);
    PyObject* _lst20 = PyList_New(a0.len);
    for (long long _i21 = 0; _i21 < a0.len; _i21++) {
    PyObject* _it22 = PyFloat_FromDouble(a0.data[_i21]);
        PyList_SetItem(_lst20, _i21, _it22);
    }
    PyObject* _pyv19 = _lst20;
    PyTuple_SetItem(args, 0, _pyv19);
    PyObject* mod = PyImport_ImportModule("padd");
    if (!mod) return ThDict_String_Float64{0, nullptr, nullptr};
    PyObject* f = PyObject_GetAttrString(mod, "describe");
    Py_DECREF(mod);
    if (!f || !PyCallable_Check(f)) { Py_XDECREF(f); return ThDict_String_Float64{0, nullptr, nullptr}; }
    PyObject* r = PyObject_CallObject(f, args);
    Py_DECREF(f);
    Py_DECREF(args);
    if (!r) { PyErr_Clear(); return ThDict_String_Float64{0, nullptr, nullptr}; }
    ThDict_String_Float64 out;
    Py_ssize_t _n23 = PyDict_Size(r);
    out.len = (long long)_n23;
    out.keys = (char**)malloc(sizeof(char*) * (size_t)_n23);
    out.values = (double*)malloc(sizeof(double) * (size_t)_n23);
    PyObject* _items24 = PyDict_Items(r);
    for (Py_ssize_t _i25 = 0; _i25 < _n23; _i25++) {
        PyObject* _pair26 = PyList_GetItem(_items24, _i25);
        PyObject* _k27 = PyTuple_GetItem(_pair26, 0);
        PyObject* _v28 = PyTuple_GetItem(_pair26, 1);
    const char* _s29 = PyUnicode_AsUTF8(_k27);
    out.keys[_i25] = _s29 ? strdup(_s29) : nullptr;
    out.values[_i25] = PyFloat_AsDouble(_v28);
    }
    Py_DECREF(_items24);
    Py_DECREF(r);
    return out;
}
} // extern C