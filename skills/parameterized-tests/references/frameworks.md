# Framework Idioms

Use the repository's existing test framework and its native parameterization mechanism. Do not introduce a new dependency solely for parameterization.

| Ecosystem | Preferred idiom | Notes |
| --- | --- | --- |
| Python / pytest | `@pytest.mark.parametrize` | Use `ids=` or `pytest.param(..., id=...)` when parameter values do not clearly identify failures. |
| Go / `testing` | Table-driven tests with `t.Run` | Use a slice or map of cases and named subtests. |
| JavaScript / TypeScript / Vitest | `test.each` or `it.each` | Prefer the repository's existing Vitest style. |
| JavaScript / TypeScript / Jest | `test.each` or `it.each` | Prefer the repository's existing Jest style. |
| Java / JUnit 5 | `@ParameterizedTest` | Use the simplest suitable source such as `@ValueSource`, `@CsvSource`, or `@MethodSource`. |
| .NET / xUnit | `[Theory]` | Use `[InlineData]`, `[MemberData]`, or the repository's established data source. |
| .NET / NUnit | `[TestCase]` or `[TestCaseSource]` | Keep each case independently reported. |
| Rust | Repository-native table or macro idiom | The standard test harness has no direct universal equivalent; do not add a crate just to parameterize tests. |
| Ruby / RSpec | Repository-native shared or data-driven examples | Do not force a new helper DSL when the project has no established parameterized-test idiom. |

## Selection Rule

Choose the narrowest native mechanism that represents the case data without introducing case-specific control flow into the test body. If the available mechanism makes the test less explicit than separate tests, keep the tests separate.
