# Documentation

Start with [installation and host setup](integrations.md). It is the canonical
guide for choosing an environment, installing, upgrading and removing integrations.

| Topic | Guide |
|---|---|
| Installation, host selection, upgrades and removal | [Integrations](integrations.md) |
| Turkish quick start | [Türkçe](README_TR.md) |
| Commands and JSON contracts | [CLI reference](cli.md) |
| Host surfaces and tested scope | [Compatibility](compatibility.md) |
| Task progress, evidence and revalidation | [Execution state](execution-state.md) |
| SDK, storage and runtime boundaries | [Architecture](architecture.md) |
| Relationship to the SKILL.state paper | [Research alignment](paper-alignment.md) |
| Security and trust boundaries | [Security](../SECURITY.md) |
| Automated checks and release evidence | [Validation](validation.md) |
| Maintainer publishing procedure | [Releasing](releasing.md) |

## Experiments

- [Codex coding experiment](benchmarks/coding-agent.md): measured correctness,
  token usage and latency; one paired trial, not a universal performance claim.
- [smolagents acceptance](smolagents-acceptance.md): external framework correctness
  and forced-process continuation.
- [Host acceptance](host-acceptance.md): observed application behavior by surface.

Reports and files under `releases/` describe the versions actually tested. Their
older version numbers are historical evidence, not current installation guidance.
Plugin folders are optional distribution assets; ordinary installation uses the
Python package and project setup commands.
