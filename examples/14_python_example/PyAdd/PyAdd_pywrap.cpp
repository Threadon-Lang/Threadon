#include <Python.h>
extern "C" {
static bool _py_init = false;
static void ensure_init() {
    if (!_py_init) {
        Py_Initialize();
        PyRun_SimpleString("import sys; sys.path.insert(0, \"/home/joep/projects/AGI/threadon/examples/14_python_example/PyAdd\")");
        _py_init = true;
    }
}
void mean(double a0, double a1) {
    ensure_init();
    PyObject* args = PyTuple_New(2);
    PyTuple_SetItem(args, 0, PyFloat_FromDouble(a0));
    PyTuple_SetItem(args, 1, PyFloat_FromDouble(a1));
    PyObject* mod = PyImport_ImportModule("padd");
    if (!mod) return;
    PyObject* f = PyObject_GetAttrString(mod, "mean");
    Py_DECREF(mod);
    if (!f || !PyCallable_Check(f)) return;
    PyObject* r = PyObject_CallObject(f, args);
    Py_DECREF(f);
    Py_DECREF(args);
    Py_DECREF(r);
    return;
}
double scale(double a0, double a1) {
    ensure_init();
    PyObject* args = PyTuple_New(2);
    PyTuple_SetItem(args, 0, PyFloat_FromDouble(a0));
    PyTuple_SetItem(args, 1, PyFloat_FromDouble(a1));
    PyObject* mod = PyImport_ImportModule("padd");
    if (!mod) return 0.0;
    PyObject* f = PyObject_GetAttrString(mod, "scale");
    Py_DECREF(mod);
    if (!f || !PyCallable_Check(f)) return 0.0;
    PyObject* r = PyObject_CallObject(f, args);
    Py_DECREF(f);
    Py_DECREF(args);
    double out = PyFloat_AsDouble(r);
    Py_DECREF(r);
    return out;
}
void normalize(double a0, double a1, double a2) {
    ensure_init();
    PyObject* args = PyTuple_New(3);
    PyTuple_SetItem(args, 0, PyFloat_FromDouble(a0));
    PyTuple_SetItem(args, 1, PyFloat_FromDouble(a1));
    PyTuple_SetItem(args, 2, PyFloat_FromDouble(a2));
    PyObject* mod = PyImport_ImportModule("padd");
    if (!mod) return;
    PyObject* f = PyObject_GetAttrString(mod, "normalize");
    Py_DECREF(mod);
    if (!f || !PyCallable_Check(f)) return;
    PyObject* r = PyObject_CallObject(f, args);
    Py_DECREF(f);
    Py_DECREF(args);
    Py_DECREF(r);
    return;
}
void describe(double a0, double a1, double a2, double a3, double a4) {
    ensure_init();
    PyObject* args = PyTuple_New(5);
    PyTuple_SetItem(args, 0, PyFloat_FromDouble(a0));
    PyTuple_SetItem(args, 1, PyFloat_FromDouble(a1));
    PyTuple_SetItem(args, 2, PyFloat_FromDouble(a2));
    PyTuple_SetItem(args, 3, PyFloat_FromDouble(a3));
    PyTuple_SetItem(args, 4, PyFloat_FromDouble(a4));
    PyObject* mod = PyImport_ImportModule("padd");
    if (!mod) return;
    PyObject* f = PyObject_GetAttrString(mod, "describe");
    Py_DECREF(mod);
    if (!f || !PyCallable_Check(f)) return;
    PyObject* r = PyObject_CallObject(f, args);
    Py_DECREF(f);
    Py_DECREF(args);
    Py_DECREF(r);
    return;
}
double add(double a0, double a1) {
    ensure_init();
    PyObject* args = PyTuple_New(2);
    PyTuple_SetItem(args, 0, PyFloat_FromDouble(a0));
    PyTuple_SetItem(args, 1, PyFloat_FromDouble(a1));
    PyObject* mod = PyImport_ImportModule("padd");
    if (!mod) return 0.0;
    PyObject* f = PyObject_GetAttrString(mod, "add");
    Py_DECREF(mod);
    if (!f || !PyCallable_Check(f)) return 0.0;
    PyObject* r = PyObject_CallObject(f, args);
    Py_DECREF(f);
    Py_DECREF(args);
    double out = PyFloat_AsDouble(r);
    Py_DECREF(r);
    return out;
}
} // extern C