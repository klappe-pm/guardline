# developer-docs

Documentation for people who change guardline: you add a rule, fix a detector, extend the shell splitter or cut a release. It is arranged by the four [Diátaxis](https://diataxis.fr/) quadrants, like the user documentation in [docs](../docs/README.md), so the folder a page sits in tells you what kind of page it is.

## tutorials

Lessons for someone who has not contributed before. [first contribution](tutorials/first-contribution.md) takes you from a clone to a merged-ready change that adds a rule with its two examples. Index: [tutorials](tutorials/README.md).

## how-to-guides

Recipes for a specific goal. [run the tests](how-to-guides/run-the-tests.md) covers the suite, coverage, linting and type checking, and [add a rule](how-to-guides/add-a-rule.md) covers adding a built-in rule and what the tests then require, and [release](how-to-guides/release.md) publishes a version to PyPI through trusted publishing. Index: [how-to guides](how-to-guides/README.md).

## reference

Lookup pages that describe the source as it is. [source layout](reference/source-layout.md) maps every module and test file, and [package data](reference/package-data.md) describes the shipped rule files and how they are read. Index: [reference](reference/README.md).

## explanation

Discussion for a reader who wants to understand the code. [architecture](explanation/architecture.md) explains how a scan flows through the modules and why each piece sits where it does. Index: [explanation](explanation/README.md).
