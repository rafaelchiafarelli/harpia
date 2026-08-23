
### Session J.25 — Android verification: message classes + JSON

- **Depends on:** J.24 merged.
- **Deliverable:** verified on an actual Android build: message classes
  (protobuf-java POJOs+builders, portable as generated); JSON
  (de)serialization, only if J.24 picked the full runtime.
- **Tests:**
  - Integration: a real Android build depending on the generated message
    classes, exercising construction/serialization on-device.
