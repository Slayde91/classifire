# Controlled source imports

Do not commit confidential supplier prices, customer data, proprietary technical reports, production evidence or secrets to the application repository.

The authorised Package 14 pricing library, Package 15 technical source library, Package 17 executable technical variants and supporting source specifications may be stored in a separately secured repository, object store or local controlled source directory.

For local migration from the reviewed CLASSIFIRE essentials archive, stage controlled material under the Git-ignored `private-data/controlled-source/` tree and import Package 14 / Package 17 through CLASSIFIRE services. Retain source hashes, release IDs, validation evidence and migration receipts.

Do not copy raw Package 14 pricing rows or the complete Package 15/17 corpus into Mission Control or general OpenClaw agent prompts. Agents access governed query services; CLASSIFIRE remains the canonical domain and library authority.
