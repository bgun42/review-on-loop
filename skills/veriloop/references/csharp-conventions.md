# C# Default Conventions Reference (Microsoft baseline)

Distilled from Microsoft's official guidance:
[.NET coding conventions](https://learn.microsoft.com/dotnet/csharp/fundamentals/coding-style/coding-conventions)
and [C# identifier names](https://learn.microsoft.com/dotnet/csharp/fundamentals/coding-style/identifier-names)
(themselves adopted from the .NET runtime and Roslyn team styles).

## When this file applies

The rule of `conventions.md` still governs: **the target repository's own precedent
always wins.** Use this file only for the gaps —

- The repo has **no precedent** on a point (new/sparse codebase, first file of its
  kind), so the diff has nothing local to match. Judge it against this baseline.
- The repo has **no linter/analyzer config** enforcing style, and you need a defensible
  standard for what "normal C#" is.
- The diff itself is inconsistent (two casings for the same kind of symbol within one
  change) — this file says which side is standard.

If the repo consistently deviates from a rule below (e.g., no `_` prefix on private
fields anywhere), that deviation is the repo's convention — do not flag diffs for
following it, and do flag diffs that "correct" it unilaterally.

## Naming

| Element | Convention | Example |
|---|---|---|
| Class, record, struct, delegate type, enum | PascalCase | `DataService` |
| Interface | PascalCase with `I` prefix | `IWorkerQueue` |
| Public members (methods, properties, events, fields) | PascalCase | `StartEventProcessing` |
| Methods and local functions (all visibilities) | PascalCase | `CountQueueItems` |
| Constants (fields and local constants) | PascalCase | `MaxRetryCount` |
| Private/internal instance fields | camelCase with `_` prefix | `_workerQueue` |
| Private/internal static fields | `s_` prefix | `s_workerQueue` |
| Thread-static fields | `t_` prefix | `t_timeSpan` |
| Method parameters, local variables | camelCase | `someNumber`, `isValid` |
| Primary constructor parameters — class/struct | camelCase (they behave like parameters) | `class DataService(ILogger logger)` |
| Primary constructor parameters — record | PascalCase (they become public properties) | `record Person(string FirstName)` |
| Generic type parameters | Descriptive name with `T` prefix; bare `T` acceptable when a single parameter is self-explanatory | `TSession`, `List<T>` |
| Attribute types | end with `Attribute` | `ValidatedAttribute` |
| Enums | singular noun; plural only for `[Flags]` | `Color` / `FileAccessOptions` |
| Namespaces | PascalCase, reverse-domain style, meaningful | `CoolStuff.AwesomeFeature` |
| Async methods | `Async` suffix (TAP convention) | `GetReportsAsync` |

General naming rules:

- Meaningful, descriptive names; prefer clarity over brevity. No abbreviations or
  acronyms unless widely recognized.
- No single-letter names except simple loop counters.
- Never two consecutive underscores in an identifier (reserved for the compiler).
- Do not encode the type into the name; the name carries semantics, the type carries
  the type.

## Layout and style

- Four-space indentation, spaces not tabs.
- Allman braces: opening and closing brace each on its own line, at the current
  indentation level.
- One statement per line; one declaration per line.
- At least one blank line between method and property definitions.
- Break long statements across lines; when wrapping, the line break goes **before**
  binary operators. Continuation lines indent one tab stop (four spaces).
- Use parentheses to make clauses of an expression explicit:
  `if ((startX > endX) && (startX > previousX))`.
- Language keywords over runtime types: `string`/`int`, not `String`/`Int32`.
- Prefer `int` over unsigned types unless the domain demands otherwise.

## Comments

- `//` single-line comments for brief explanations; avoid `/* */` blocks for prose.
- Comment on its own line, not at the end of a code line.
- Start with a capital letter, end with a period, one space after `//`.
- Public types and members get XML doc comments (`///`).

## `var` — implicit typing

- Use `var` only when the type is obvious from the right-hand side: a `new` expression,
  an explicit cast, or a literal. `var message = "text";` is fine;
  `var result = ExampleClass.ResultSoFar();` is not — a method name never makes the
  type "obvious".
- Use `var` for `for` loop counters; use **explicit types** in `foreach` (the element
  type of a collection is rarely obvious from its name).
- Use `var` for LINQ query results (anonymous types and nested generics make explicit
  types unreadable) — this overrides the general rule.
- Never use `var` when only `dynamic` (deliberate runtime typing) is meant.

## Language usage

- **Strings**: interpolation (`$"{x}, {y}"`) for short concatenations;
  `StringBuilder` for loops over large amounts of text; raw string literals (`"""`)
  over escape sequences and verbatim strings.
- **Collections**: initialize with collection expressions — `string[] vowels = ["a", "e", "i"];`.
- **Constructors/initialization**: object initializers over sequential property
  assignment; `required` properties over constructor enforcement where applicable.
- **Delegates**: use `Func<>`/`Action<>` instead of declaring custom delegate types;
  compact instantiation (`Del d = Method;`); lambdas for event handlers you never
  need to detach.
- **Resource cleanup**: `using` statement (or the braceless `using` declaration) instead
  of `try/finally` whose `finally` only calls `Dispose`.
- **Boolean operators**: `&&`/`||`, not `&`/`|`, in conditionals — short-circuit
  evaluation prevents evaluating a right-hand clause whose precondition (e.g., a
  non-zero divisor) the left-hand clause just checked.
- **Instantiation**: concise forms (`var x = new Thing();` or `Thing x = new();`) when
  the variable type matches the created type.
- **Static members**: call via the class name (`ClassName.StaticMember`); never qualify
  a base-class static through a derived class name.
- **Exceptions**: catch only exceptions you can meaningfully handle, always a specific
  type — never bare `System.Exception` without an exception filter.
- **Async**: async/await for I/O-bound work; be deliberate about `ConfigureAwait`
  in library code (deadlock avoidance).
- **LINQ**: meaningful query-variable names (`seattleCustomers`); PascalCase aliases
  for anonymous-type properties; rename ambiguous result properties
  (`CustomerName`, not `Name`); put `where` before other clauses; `join` over nested
  `from` for inner collections; align clauses under `from`.
- **Namespaces**: file-scoped declarations (`namespace X;`); `using` directives
  **outside** the namespace declaration (inside, resolution becomes relative and a
  later sibling namespace can silently capture the reference and break the build).
- **Modernity**: prefer current language idioms over superseded constructs; a diff that
  introduces an outdated pattern next to modern code is worth a note even under this
  baseline.

## Enforcement note

If the repo has an `.editorconfig` or analyzers configured, run them (`dotnet format
--verify-no-changes`, `dotnet build` with analyzers) instead of eyeballing these rules —
the tool's verdict on configured rules is exact and beats this checklist. This file is
for what no tool in the repo enforces.
