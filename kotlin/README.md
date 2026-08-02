# remotetable Kotlin (Android / VE)

M1 surface mirrors Python/Go ops:

- `RemoteTable` + `Backend`
- Backend ids: `google-sheets`, `excel-graph`, `ethercalc`
- Mock backend for conformance until AAR packaging lands

## Artifact

VE expects `third_party/remotetable/artifact/remotetable.aar` built from this tree (or mirrored `build` recipe). Until the AAR pipeline is wired, VE keeps in-tree tabular backends for production and uses this API as the cutover target.

## Conformance

Same fixtures as `conformance/fixtures/mock_book.json`. JVM unit tests can be added under `kotlin/src/test` when Gradle module is fully scaffolded.
