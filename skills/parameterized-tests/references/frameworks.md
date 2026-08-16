# Framework Idioms

Use the repository's existing test framework and native parameterization mechanism.

- Python / pytest: `@pytest.mark.parametrize`; use `ids=` or `pytest.param(..., id=...)` when raw values are unclear.
- Go / `testing`: table-driven tests with named `t.Run` subtests.
- JavaScript / TypeScript / Vitest or Jest: `test.each` or `it.each`.
- Java / JUnit 5: `@ParameterizedTest` with the simplest suitable source (`@ValueSource`, `@CsvSource`, or `@MethodSource`).
- .NET / xUnit: `[Theory]` with `[InlineData]` or `[MemberData]`.
- .NET / NUnit: `[TestCase]` or `[TestCaseSource]`.
- Rust: use the repository's established table or macro idiom.
- Ruby / RSpec: use the repository's established shared or data-driven examples.

Use the narrowest native idiom that keeps the shared test body free of case-specific control flow; otherwise keep the tests separate.
