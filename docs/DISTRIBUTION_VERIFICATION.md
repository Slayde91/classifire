# Distribution verification

The installed application needs its Python modules, Jinja templates and static UI
resources. A source-checkout test can pass while the built wheel omits resources.
The reproduced defect omitted all 67 templates and 19 static files, including the
native chat panel assets and CLASSIFIRE branding.

`pyproject.toml` now declares the existing resource paths as package data. This
changes distribution contents only: no domain logic, dependency versions, database
schema or approval boundary changes.

CI builds the wheel before the full test suite and runs:

```text
python -m pip wheel --no-deps --wheel-dir <wheel-directory> .
python scripts/verify_distribution.py <wheel-directory>
```

The verifier requires exactly one wheel and compares every non-bytecode application
file under `src/classifire` against its packaged member and exact bytes. It rejects
missing or unexpected application members, altered bytes, duplicate members, unsafe
archive paths and linked source resources. Distribution metadata is outside this
source-byte comparison. Keep source resources reviewed; the checker does not confer
permission to publish new private files. All existing CI checks remain required.

When adding a new resource type or directory, update package-data declarations and
run the actual wheel check. Do not suppress the missing-file failure.

Local verification for this change passed 15 packaging/migration tests, full Ruff
and scoped Bandit. The corrected wheel retained all 326 package files exactly.
An isolated installation imported from the installed target, compiled all 67
Jinja templates and served the login page, all 19 static resources and the brand
route through TestClient. Returned asset bytes matched the installed files; the
application check used an existing disposable15433 database with an unchanged full
dump. No listener, live database, provider request or deployment was involved.

These checks do not prove rendered-browser appearance, clean-machine dependency
installation, report accuracy or production readiness. The private wheel used the
existing validated Python environment for dependencies. Live activation remains
subject to its separate approved backup, restore, migration and rollback plan.


The combined restart/packaging candidate then passed all78 affected tests and the
same326-file wheel comparison. Its71-wheel dependency set installed offline into a
fresh Windows Python environment with system/user site-packages disabled and the
tested dependency constraints preserved. `pip check` passed. Two fresh processes
imported the installed package, compiled67 templates and served all19 assets with
unchanged disposable15433 database dumps. Five fresh installed Word/XLSX worker
modes produced exact source-reference outputs while refusing unrelated application
imports. These results strengthen installation evidence; they do not certify a
separate machine, rendered browser, scanner/provider execution or live activation.
