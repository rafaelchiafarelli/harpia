## XML example

- **Depends on:** task 1.
- **Deliverable:** `HarpiaTest/app_example/xml_demo/` — `harpia::xml::to_xml`/`from_xml`
  round-trip + `<name>_xsd()` dump, reusing `shipment`/`parcel` (already
  in the restructured fixture, exercises nested + repeated embed-flatten
  — no new message needed).
- **Tests:** build + run inside `Docker/run.sh`; assert the round-tripped
  value matches the original.

