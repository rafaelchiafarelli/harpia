# cpp-zmq-header-odr-DEFECT — epics

One epic: **`zmq-shared-runtime`**, one task.

```
1-guard-shared-zmq-definitions
```

## Definition of done

- A C++ program including every generated `zmq/*_zmq.h` compiles and links.
- Golden diff shows only the guard / move of the shared definitions.
- Full Docker suite green before merging up to `dev`.
