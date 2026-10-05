# Product direction

Starshine exists to make bounded vector-analysis workflows **inspectable before they run and
reproducible after they run**.

That is the product. The HTTP server, browser workbench, operator catalog, manifests, CI evidence,
and release machinery are useful only when they strengthen that outcome.

## Problem

Small spatial-analysis workflows often fail in ways that are easy to miss or hard to hand off:

- CRS assumptions are implicit or discovered only after a wrong result;
- geometry and property requirements live in a person's head rather than in a contract;
- desktop or notebook state makes a workflow difficult to reproduce elsewhere;
- a script can complete without leaving enough evidence to explain exactly what ran;
- another person receives files and commands but cannot quickly determine whether the inputs satisfy
  the workflow's assumptions.

Starshine turns those hidden assumptions into deterministic contracts, Preflight findings, workflow
semantics, and provenance evidence.

## Who it is for now

The current bounded product is useful for three concrete situations:

1. **Research and teaching handoff.** A small vector workflow should be understandable and repeatable
   on another machine without relying on hidden desktop state.
2. **Spatial CI and review.** A repository or data pipeline should be able to check Workflow, CRS,
   geometry, and field requirements before an analysis is executed.
3. **Lightweight integration.** A script, notebook, or later a browser client should be able to ask a
   stable service what a workflow needs and whether supplied data satisfies it.

These scenarios all reward the same property: deterministic assurance around a bounded workflow.

## What Starshine is not trying to become

Current development should not optimize for:

- replacing QGIS or ArcGIS desktop editing, cartography, or interactive data management;
- matching a large GIS library's operator count;
- raster or remote-sensing processing;
- arbitrary Python, shell, plugin, or module execution;
- database-scale or distributed geoprocessing;
- accounts, billing, collaboration, or SaaS infrastructure before actual use requires them.

Those may be separate products or future adapters. They are not evidence of progress by themselves.

## Product sequence

The order matters:

`describe → validate → plan → contract → preflight → execute → manifest → reproduce`

The platform follows the same sequence:

1. expose data-free workflow review;
2. accept bounded real data for Preflight;
3. add bounded execution only after its resource boundary is credible;
4. add a browser workbench only when it makes the same contracts and findings easier to use;
5. add persistence, queues, databases, and collaboration only after measured use makes them necessary.

This is why data-aware Preflight comes before upload workflows, task queues, or a polished UI.

## Success measures

A change is useful when it improves one or more of these properties:

- **earlier failure:** invalid CRS, geometry, or field assumptions are found before spatial execution;
- **same semantics everywhere:** Python, CLI, HTTP, and future Web surfaces report the same Core
  contracts and diagnostics rather than implementing competing rules;
- **reproducible evidence:** the same Workflow and inputs produce stable digests, reports, and
  manifests suitable for handoff;
- **bounded operation:** resource limits and supported formats are explicit instead of implied;
- **clean distribution:** the capability works from the exact built wheel, not only from a source
  checkout;
- **lower handoff cost:** another person can determine what is required, what failed, and what ran
  without reconstructing local state.

Operator count, module count, endpoint count, and UI surface are not success measures.

## Decision filter for new work

Before adding a feature, answer four questions:

1. Which target scenario needs it?
2. Which hidden assumption or handoff problem does it remove?
3. Can it reuse the existing registry, Workflow, Preflight, execution, and evidence spine?
4. What concrete test proves the new surface agrees with the Core?

If those questions have weak answers, the feature should remain out of scope.

Issue #128 tracks the first platform increment built under this product filter.
