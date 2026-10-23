# Reference

Reference pages describe the machinery as it is, organised around the thing described, complete and free of instruction. Look here for an option, a field, a rule or a function. To learn a task use the [Tutorials](../tutorials/README.md) and [How-To Guides](../how-to-guides/README.md), and for the reasons behind the design see [Explanation](../explanation/README.md).

## Pages

- [CLI](cli.md): every subcommand and option of the `guardline` command, including `init` and `config show`, and its exit statuses.
- [Configuration](configuration.md): every key in `guardline.toml` and `[tool.guardline]`, and how the file is found.
- [Rule File Format](rule-file-format.md): every field of a rule and every check the loader makes.
- [Rules](rules.md): all 43 built-in rules by family, with scope and description.
- [Hook Protocol](hook-protocol.md): the payload the hook reads, the fields it judges and the decision it writes.
- [Python API](python-api.md): every public function and class of the package.
- [Package Data](package-data.md): the shipped rule files, how they are read and how they are built into the wheel.
- [Source Layout](source-layout.md): every module, repository file and test file, with the one job it has.
