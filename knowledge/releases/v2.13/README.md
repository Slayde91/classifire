# CLASSIFIRE v2.13 Governed Knowledge Release

This directory contains the governed release metadata for the reviewed CLASSIFIRE v2.13 knowledge corpus.

## Authority and preservation

- Original Packages 01–10, 12 and 14–18 remain immutable controlled source evidence.
- Runtime authority comes from approved immutable CLASSIFIRE database releases and their verified manifests.
- Package 15 is the **FIREFLY Technical System Library**; Package 17 contains its executable FIREFLY variants.
- The umbrella technical authority is the **CLASSIFIRE Technical Authority Registry**.
- Package 14 is commercial pricing evidence only and cannot establish technical applicability.
- Corrections to retained source wording are governed through amendments/overlays and later source releases rather than silent edits.

## Files

- `CLASSIFIRE_KNOWLEDGE_RELEASE_MANIFEST_v2.13.json` — governed release manifest.
- `../../manifests/classifire-knowledge-source-v2.13.json` — reviewed source filenames, counts, hashes and known anomalies.
- `../../amendments/CLASSIFIRE_KNOWLEDGE_ALIGNMENT_AMENDMENT_v2.13.1.md` — implementation alignment overlay.
- `../../../docs/CLASSIFIRE_ARCHITECTURE.md` — current implementation architecture.
- `../../../docs/CLASSIFIRE_ROADMAP.md` — active delivery and release roadmap.

## Private source archive

The reviewed source corpus is packaged as:

`knowledge/source/CLASSIFIRE_Knowledge_Source_Pack_v2.13.zip`

Expected SHA-256:

`75cccd7a33b84b276bbc47820f204b020151553d410dad73cc0d39c2ce2f925e`

Expected size: `7,514,016` bytes. The archive contains 16 reviewed source files.

The ordinary repository `.gitignore` intentionally excludes `knowledge/source/**`. Publication is an explicit controlled exception and must use Git LFS through:

```powershell
.\scripts\publish_classifire_knowledge_source_pack.ps1 -SourcePackPath <path-to-governed-zip>
```

Add `-CommitAndPush` only after the staged LFS pointer and repository visibility have been reviewed.

The repository must remain private. Do not publish the source archive to a public repository, agent prompt, Mission Control task body or client output.
