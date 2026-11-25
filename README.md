# dreck

dreck scores the functions of a project with the CRAP metric and prints them worst first, each with its location, so the function behind a high score can be opened without searching for it. It reads F# (`.fs`, `.fsx`), Kotlin (`.kt`) and Swift (`.swift`); `dreck --help` lists the languages it knows.

CRAP is `CC² × (1 − coverage)³ + CC`, where `CC` is the function's cyclomatic complexity (the number of paths through it) and `coverage` the share of it its tests run. A high score means complex and under-tested. Coverage comes from reports your own test run wrote, passed with `--coverage-report`; without one, dreck prints each function's complexity, with `-` for coverage and CRAP.

dreck starts no test run and writes no file.

## Install

dreck lives at `https://github.com/felipearpa/dreck`. To put the `dreck` command on your `PATH`:

```bash
uv tool install git+https://github.com/felipearpa/dreck
```

`uv tool upgrade dreck` brings a later version. Then run `dreck` where this README shows `uv run dreck`.

To work on dreck itself, from a clone:

```bash
uv sync
```

Either way, the first run in each language downloads that language's parser, so it needs network.

## Usage

```bash
uv run dreck [path-or-fragment ...]
```

Prints one line per function. `uv run dreck tests/fixtures/kotlin` prints:

```
crap -  cc 3  cov -  tests/fixtures/kotlin/Orders.kt:4-8  total
crap -  cc 3  cov -  tests/fixtures/kotlin/Orders.kt:10-14  label
crap -  cc 1  cov -  tests/fixtures/kotlin/Orders.kt:17-19  describe
```

Each line carries a label beside each number, so a line still reads on its own when the output is cut by `head`, filtered by `grep` or quoted alone:

- `crap`: the CRAP score with one decimal, or `-` when coverage was not measured (see [Coverage reports](#coverage-reports)).
- `cc`: the cyclomatic complexity.
- `cov`: the coverage with one decimal and `%`, or `-` when not measured.
- the location, `file:start-end`: the file relative to the current directory (absolute when it lies outside it), and the function's first and last lines.
- the name, last because some languages allow spaces in it: the function's own, without its class or package. Two functions can share a name (overloads, or `equals` in two classes), so a function is identified by its location.

Lines with a CRAP score come first, worst first; functions without one follow, most complex first. Equal lines are ordered by path, then by first line. When no file is selected, dreck prints `No source files to analyze.`

With no argument, the current directory is scored. An argument that names an existing file or folder is scored instead. Any other argument is a fragment: only files whose path, as the report prints it, contains it are scored, so a fragment naming a folder above the current directory matches nothing. A path that does not exist is read as a fragment too: a misspelled path usually matches nothing, and dreck prints `No source files to analyze.` and still exits 0.

Examples, run from this repository:

```bash
uv run dreck                                   # score the current directory
uv run dreck tests/fixtures/kotlin             # score one folder
uv run dreck tests/fixtures/kotlin/Orders.kt   # score one file
uv run dreck tests Orders                      # score tests, only paths containing "Orders"
uv run dreck tests/fixtures/kotlin --coverage-report tests/fixtures/kotlin/kover.xml
uv run dreck tests/fixtures/swift --coverage-report tests/fixtures/swift/lcov.info
uv run dreck tests/fixtures/fsharp --coverage-report tests/fixtures/fsharp/coverage.cobertura.xml
uv run dreck --changed                         # score the files changed since the last commit
uv run dreck --changed-functions               # score the functions changed since the last commit
uv run dreck --changed-functions tests/fixtures/kotlin --coverage-report tests/fixtures/kotlin/kover.xml
uv run dreck --help
```

Options:

- `-h`, `--help`: print the help, with each language and its file extensions, and exit 0.
- `--coverage-report <path>`: read coverage from this report file, or from every report in this folder; may be repeated. See [Coverage reports](#coverage-reports). `uv run dreck tests/fixtures/kotlin --coverage-report tests/fixtures/kotlin/kover.xml` prints:

  ```
  crap 4.1  cc 3  cov 50.0%  tests/fixtures/kotlin/Orders.kt:10-14  label
  crap 3.1  cc 3  cov 75.0%  tests/fixtures/kotlin/Orders.kt:4-8  total
  crap 2.0  cc 1  cov 0.0%  tests/fixtures/kotlin/Orders.kt:17-19  describe
  ```

  and `uv run dreck tests/fixtures/swift --coverage-report tests/fixtures/swift/lcov.info` prints:

  ```
  crap 4.1  cc 3  cov 50.0%  tests/fixtures/swift/Orders.swift:4-8  total
  crap 3.3  cc 3  cov 66.7%  tests/fixtures/swift/Orders.swift:10-16  label
  crap 2.0  cc 1  cov 0.0%  tests/fixtures/swift/Orders.swift:19-21  describe
  ```

  and `uv run dreck tests/fixtures/fsharp --coverage-report tests/fixtures/fsharp/coverage.cobertura.xml` prints:

  ```
  crap 3.3  cc 3  cov 66.7%  tests/fixtures/fsharp/Orders.fs:7-11  label
  crap 2.5  cc 2  cov 50.0%  tests/fixtures/fsharp/Orders.fs:3-5  total
  crap 2.0  cc 1  cov 0.0%  tests/fixtures/fsharp/Orders.fs:13-13  describe
  ```

- `--changed`: score only the files git reports as added, modified or untracked, among the files the paths, fragments and skips select. A deleted file is left out, and a renamed one is its new name.
- `--changed-functions`: score only the functions holding a line changed since the last commit (`git diff HEAD`, staged or not), and every function of an untracked file, among the files the paths, fragments and skips select. A deletion counts as a change to the line above it. Before the repository's first commit, every function of a changed file is scored. It implies `--changed`.

  The coverage rule is applied to every function of the changed files before the others are dropped, so a function prints the numbers a run without the option gives it, as long as the reports cover its language in those files.

With either option, git is asked where the files are: in each folder named as an argument, or a named file's folder, or the current directory when no path is named. A run inside one folder of a larger repository therefore scores only that folder's changed files: a change elsewhere in the repository is not scored, nor a changed file the skips leave out, such as a test file, unless it is named as an argument. A path in another repository reads that repository's changes. Only the changed files are passed to the reports, so Xcode derived data converts only them. On a clean tree nothing is selected: dreck prints `No source files to analyze.` before reading any report and exits 0, even when a `--coverage-report` path does not exist.

Exit codes:

- `0`: the run finished, also when nothing was selected.
- `1`: a bad option, which prints the reason and the help on standard error; `--changed` or `--changed-functions` outside a git repository, or git failing otherwise, which prints `dreck: --changed needs git status: <git's reason>` (or `dreck: --changed-functions needs git: …`) and no report; or, with a file to score, a `--coverage-report` path that does not exist, holds no report dreck reads, names a report that cannot be parsed, or is Xcode derived data that cannot be converted, which prints the reason on standard error and no report.

### Coverage reports

dreck starts no test run and finds no report on its own: it reads the reports passed with `--coverage-report`, a file or a folder, relative to the current directory. Pass the reports your test run left after the edits being scored; dreck cannot tell a stale report, and a function whose lines moved since is scored on what the report says.

| Language | Report to pass | How a function is found in it |
|---|---|---|
| F# | the Cobertura reports `dotnet test --collect:"Code Coverage;Format=cobertura"` writes, one per test project (a folder holding them all can be passed) | by its file and line range: the share of the conditions on its lines that ran when the report gives `condition-coverage` there, otherwise the share of its lines that ran. A file the reports list with no line in the function's range scores 0%. |
| Kotlin | Kover's XML report (`build/reports/kover/report.xml`), or a JaCoCo XML report | by its JVM class (`pkg.Outer$Inner`, or `pkg.FileKt` and `@file:JvmName` for a top-level function) and its name; the instructions of every method the function compiles into add up: its own, a value-class mangling (`name-<hash>`) and its lambdas, default-argument bridges and `internal` suffixes (`name$…`). Kover writes no line numbers, so overloads share one percentage. |
| Swift | Xcode derived data: the folder `xcodebuild test -enableCodeCoverage YES -derivedDataPath <folder>` leaves, or the folder right above it; or the export `swift test --enable-code-coverage` writes (`swift test --show-codecov-path` names it); or an LCOV file | by its file and line range: the share of the branches on its lines that ran when the report has LCOV branch records there, otherwise the share of its executable lines that ran. A file the reports list with no executable line in the function's range scores 0%. |

A report is told by its content, not its name:

- XML whose root is `coverage` is a Cobertura report. Each file it names is kept under its path relative to the current directory (a relative path in the report is kept as written); a file outside the current directory, such as the F# core library's sources, and a Windows path with a drive are left out.
- XML whose root is `report` is a JaCoCo or Kover report.
- Text with an `SF:` record is LCOV.
- JSON whose `type` is `llvm.coverage.json.export` is an llvm-cov export, as `swift test --enable-code-coverage` writes; it is read without `xcrun`.
- A folder holding `Build/ProfileData/<device>/*.profdata`, or one folder above such a folder, is Xcode derived data. It is not searched for other reports (its package checkouts hold report-like fixtures): each profile is converted in memory with `xcrun llvm-cov export` against the test bundles and apps built beside it in `Build/Products`, with `xcrun lipo` choosing each binary's architecture. This needs macOS with Xcode; it starts no test run and writes no file.

In a folder, files that are no report are skipped quietly. Methods of one class add up across reports, and a file reached twice, as a folder and by name, is read once. The line counts of derived data and exports add up line by line, whatever the order the paths are given in, so a line is covered when any of them covered it; only the files being scored are kept from them. Cobertura reports merge line by line: a line is covered when any report covered it, and its conditions keep the highest counts any report gives, whatever the order the reports are read in. Of two LCOV records of one file, the last read wins. Counts from derived data or an export are kept under each file's absolute path, so they replace only an LCOV record written under that same absolute path; an LCOV record that names the file otherwise stays beside them, and one that names it as dreck prints it, relative to the current directory, is found before them. A Cobertura record, kept under the file's path relative to the current directory, replaces an LCOV record written under that same path, so for one file Cobertura wins over LCOV.

A report path is matched to a source file by path, not by name alone: an exact path wins (as written, absolute, or without a leading `src/`); otherwise a report path that ends with the source's path wins, the one with the fewest extra folders, and two equally close match nothing; otherwise a report path that is a shorter tail of the source's path matches when no other source file ends with it. A report path never goes to a shorter source path when a longer source file matches it better, so `b/main.swift` does not take the record of `a/b/main.swift`.

Which functions get a number:

- Once a report holds one of a language's classes or files, every function of that language gets coverage and CRAP: a function the reports leave out scores 0%, so it sorts with the other scores instead of sinking among the unmeasured.
- A language none of whose classes or files is in a given report prints `-`, with one hint on standard error naming the reports to pass for it.
- Without `--coverage-report`, every function prints `-` and no hint is printed: that is the ordinary complexity-only run.

### Reading the report from an agent

A project whose agents run dreck can paste this paragraph into its `AGENTS.md`:

> dreck prints one line per function, worst first: `crap <score>  cc <complexity>  cov <coverage>  <file>:<start>-<end>  <name>`. `-` for `crap` and `cov` means coverage was not measured for that function; those lines follow the scored ones, most complex first. `cov 0.0%` means the reports cover the function's language but not the function. The file is relative to the folder dreck ran in, not to the repository root. Cite a function by its location, not by its name: two functions can share a name. `No source files to analyze.` means nothing was selected; with `--changed-functions`, that the working tree holds no uncommitted change in the folder. dreck writes no file.

### What is skipped

Folders `.git`, `.hg`, `.svn`, `.idea` and `.vscode` are never scanned.

For F#, `.fs` and `.fsx` files are read (not `.fsi` signatures), and these are skipped at any depth below the scanned folder: .NET build output in `bin` and `obj` folders; test code in folders named `test` or `tests`, or whose name ends in `.Test` or `.Tests` (`Demo.Tests/`). A file or folder named as an argument is scored even so: `dreck Demo/test` scores test code. The scanned folder's own name never causes a skip, so a project checked out in a folder called `test` or `bin` is scanned.

For Swift, these are skipped at any depth below the scanned folder: tool output and checkouts in `.build`, `DerivedData`, `Pods` and `Carthage` folders; any folder or file whose name ends in `Tests` or `Tests.swift` (`Tests/`, `AppTests/`, `AppUITests/`, `BoardTests.swift`); and the package manifest, `Package.swift`. A file or folder named as an argument is scored even so: `dreck AppTests` scores test code, and a named `Package.swift` is scored. The scanned folder's own name never causes a skip.

For Kotlin, only `.kt` files are read (not `.kts` scripts), and these are skipped: `build` folders above `src/` (a package folder called `build` inside `src/` is scored); `.gradle` folders at any depth below the scanned folder; any source set under `src/` whose name contains "test" (`test`, `androidTest`, `commonTest`, `testFixtures`); files ending in `Test.kt`, `Tests.kt` or `Spec.kt`. Scoring `src` still skips its test source sets, but a test file or test folder named as an argument (`src/test`) is scored; inside a named folder, files ending in `Test.kt`, `Tests.kt` or `Spec.kt` are still skipped unless they are named themselves. The scanned folder's own name never causes a skip: a project checked out in a folder called `build` is scanned. Run dreck from the module or project root, not from inside a source set: scanning `src/main` directly, a package folder called `build` is taken for build output and skipped.

A folder below the scanned folder that holds no project source of any language is never entered, whichever language names it: `.build`, `DerivedData`, `Pods` and `Carthage` (Swift), `.gradle` (Kotlin), `bin` and `obj` (F#). This holds for every language's files: a Kotlin or F# file inside a SwiftPM checkout in `.build` is not scored, and a source folder of any language that has one of these names, such as a package folder called `bin` or `obj`, is left out with everything in it. Any other folder is left out of the walk only when every language skips it; a file inside it is still skipped by its own language's rules.

### Standard error

Apart from the reason and help printed for a bad option, every line dreck prints on standard error starts with `dreck:`.

A `--coverage-report` path that does not exist, holds no report dreck reads, or names a report that cannot be parsed stops the run with exit 1 and only its reason, for instance:

```
dreck: --coverage-report build/reports/kover/report.xml: no such file or folder.
```

When no file is selected, as with `--changed` or `--changed-functions` on a clean tree, dreck prints `No source files to analyze.` before reading any report, so a report path that does not exist is not an error then.

Xcode derived data that cannot be converted stops the run the same way, naming the profile and why: `xcrun` is not installed, as on Linux; no test bundle or app was built beside the profile; or `llvm-cov` failed, with its own message:

```
dreck: --coverage-report target/DerivedData: cannot convert Xcode derived data: xcrun is not installed, so the Xcode coverage profiles … cannot be read.
```

These warnings may be printed; the report is printed in full either way:

- `dreck: <file>: unreadable <format> report (<reason>); skipped.`: a damaged report inside a given folder, where `<format>` is `Cobertura`, `JaCoCo or Kover`, `LCOV` or `llvm-cov JSON export`; the folder's other reports are read.
- `dreck: <file>: Cobertura report with branch lines that ran and carry no condition-coverage, …`, once per report: the report marks a line as a branch that ran but gives no condition counts, as a solution-wide `dotnet test` leaves when it merges its test projects' reports, so the functions on those lines may score wrongly. Running `dotnet test` with `VSTEST_DISABLE_ARTIFACTS_POSTPROCESSING=1` keeps one report per test project.
- `dreck: lipo could not read the architecture of <binaries>; llvm-cov gets no -arch.`: derived data is still converted, without naming an architecture.
- `dreck: --coverage-report <path>: matches none of the files being scored; was it made in another checkout or for another project?`: no report at that path holds one of the functions scored. With `--changed` or `--changed-functions`, only the changed files are scored, so the question ends `…, or before the files changed?`: a report made before a file was added holds none of its functions, and for Kotlin neither does one made before all of an edited file's classes were added. An edited file the report still holds, by path for F# and Swift or by class for Kotlin, is matched instead, and its functions the report lacks score 0%.
- `dreck: Kotlin: coverage and CRAP show -; no coverage report given matches its files. Pass --coverage-report <Kover's XML report>.`, for Swift `… Pass --coverage-report <Xcode derived data or a swift test export>.`, or for F# `… Pass --coverage-report <the Cobertura reports of dotnet test>.`: one hint per language none of whose classes or files is in a given report.

Each file the grammar cannot fully parse is named in a warning (`dreck: <file> has parse errors; scored as parsed`); the functions it could read are still scored. A source file dreck cannot open, for lack of permission for instance, is named on standard error (`dreck: <file> cannot be read; skipped`) and left out. Each run ends with one summary line, whose count of files scanned leaves out the files that could not be read, and whose count of functions is the lines printed (with `--changed-functions`, the functions holding a changed line):

```
dreck: 468 files scanned, 1251 functions scored, 0 files with parse errors, 0.40s
```

## What F# counts

A function is a `let` function at module or type level, a member, an active pattern (named by its pattern text, `|Even|Odd|`), a lambda bound to a value (`let handler = fun …` or `= function …`), or a value bound to an object expression, which carries the complexity of its members. A function, lambda or object expression inside another stays part of it. Other values, such as a partial application or a composition, are not scored. `let Some y = opt` and other `let`s whose name starts with a capital letter are read as union-case patterns, not functions.

Its complexity is 1, plus one for each `if`, `elif`, `for` (also `for … ->`), `while`, `when` guard on an arm, `&&` and `||`; one for each arm of a `match`, `match!` or `function` other than the first, since a `match` is taken to cover its type; and one for each handler of `try … with`. Arms on one line count as arms on their own lines do. `let!` and combinators such as `Option.map` add nothing.

## What Kotlin counts

A function is a `fun` with a body, block or expression, that is not inside another function, a lambda or an anonymous object; a local function, lambda or anonymous object stays part of the function around it. Constructors, `init` blocks, property accessors and abstract functions are not scored.

Its complexity is 1, plus one for each `if`, `for`, `while`, `do … while`, `catch`, `&&`, `||`, `?:` and `?.`, and one for each `when` arm other than `else`.

## What Swift counts

A function is a `func`, an `init`, a `deinit` or a `subscript` with a body, or a property with a body: a computed property (its getter and setter are one function), a property with `willSet` or `didSet`, or a property initialised by a closure (`lazy var cache = { … }()`). Its name is the function's or the property's, or `init`, `deinit` or `subscript`. A function, closure or type inside another function stays part of it. Protocol requirements, which have no body, are not scored.

Its complexity is 1, plus one for each `if`, `guard`, `for`, `while`, `repeat … while`, `catch`, `&&`, `||`, `??`, ternary `? :` and optional chaining `?.`; one for each `switch` case other than `default` (`case .a, .b:` counts once); one for each comma between the conditions of an `if`, `guard` or `while`; and one for each `where` on a `for`, a `case` or a `catch`. `try?`, `as?` and `init?` add nothing.

## Adding a language

A language is one file, `src/dreck/languages/<language>.py`, exposing `SPEC`, a `LanguageSpec` (`src/dreck/spec.py`), and its tests. No list names the languages: dreck finds every module in that folder, so the new file is all it takes for `dreck --help` to list the language and for its files to be scored. The spec answers:

- `name`: the language as the help and the hints print it (`F#`).
- `extensions`: the file extensions it reads (`.fs`, `.fsx`).
- `skips`: whether a file or folder below the scanned folder is left out (test code, build output, dependencies). It gets the path starting with the scanned folder's own name, which is context only, never a reason to skip.
- `prunes` (optional): folders that hold no project source of any language, such as the language's build output or dependency checkouts. The walk enters none of them below the scanned folder, for every language, so name only folders no language keeps code in.
- `functions`: the functions of one file, given its text and its path as the report prints it, each with its name, complexity and lines, and whether the grammar could not fully parse the file. `src/dreck/treesitter.py` parses with the language pack's grammar and counts complexity from a decision test.
- `reports`: in words, the reports to pass for the language, for its hint.
- `lookup`: how its functions are found in the reports: `BY_FILE_LINES` for a report by file and line, `BY_JVM_CLASS` for one by JVM class and method (`src/dreck/coverage.py`). A report format dreck does not read yet is added to `coverage.py`, named after the format, not the language.

The engine, `src/dreck/*.py`, names no language: `tests/test_engine.py` fails when an engine module names one, its module or one of its extensions below its first-line origin comment. The README's sections on what is skipped, what each language counts and its reports change in the same change.

## Credits

dreck is cut from [crapper](https://github.com/felipearpa/crapper), a fork of [unclebob/crapper](https://github.com/unclebob/crapper) by Robert C. Martin, released under the 0BSD licence: the CRAP formula, its rounding and the coverage rule (`crap.py`), the report format detection, the Cobertura, JaCoCo, Kover and LCOV readers, the matching of report paths to source files and the lookups by JVM class and by file and line range (`coverage.py`), the conversion of Xcode derived data and the reading of llvm-cov exports (`llvm.py`), the data types (`model.py`), the `complexity` helper (`treesitter.py`) and the F#, Kotlin and Swift readers (`languages/fsharp.py`, `languages/kotlin.py`, `languages/swift.py`) are copied or adapted from it, and the F# skip rules are written from its rules. Its shape comes from [doppel](https://github.com/felipearpa/doppel): the language specs and their discovery (`spec.py`, `discover.py`), the tree-sitter helpers (`treesitter.py`), the reading of files and the printing of paths (`scan.py`, `paths.py`), the command line (`cli.py`), what git reports as changed (`changed.py`) and the Kotlin and Swift skip rules are copied or adapted from it. doppel took its folder walk, tree-sitter helpers, file reading, command line and git code from [dryer](https://github.com/unclebob/dryer) by Robert C. Martin, also under the 0BSD licence, so those files descend from dryer too. Each copied file names the file it came from, and dryer's beside doppel's where doppel took it from dryer.
