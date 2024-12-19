# v 2.3.0 (?)
Changes in this release:
- Improve the overview of all handlers in the documentation. All entities sharing the same handler class are grouped together.

# v 2.2.0 (2024-12-17)
Changes in this release:
- Generate the associated environment variable to each configuration option in the reference page.

# v 2.1.1 (2024-10-08)
Changes in this release:
- Make the doc generation compatible with iso8

# v 2.1.0 (2024-08-21)
Changes in this release:
- Make compatible with iso8

# v 2.0.0 (2024-08-05)
Changes in this release:
- Use the README.md file to control what is included in the documentation. Use `--autodoc-only` to restore the previous behavior.
- Update command to generate module documentation:
    - replaced `--file` argument with `--out-dir` to support multi-file docs
    - renamed `--module_repo` to `--module-sources`
    - renamed `--module` to `--module-name`

# v 1.11.0 (2024-08-02)
This release was yanked and rereleased as 2.0.0 due to breaking changes in the interface

# v 1.10.0 (2024-06-12)
Changes in this release:
- Use system pip index to install modules
- Add the ability to filter using regexes for very large modules

# v 1.9.0 (2024-01-25)
Changes in this release:
- Drop iso4/iso5 support
- Support the new arithmetic operators in the lexer

# v 1.8.0 (2023-09-12)
Changes in this release:
- Fix lexer bug not recognizing simple quotes as a valid string delimiter.

# v 1.7.0 (2022-12-20)
Changes in this release:
- Ensure that environment settings defined by Inmanta extensions are present in the generated documentation.
- Try to load all modules provided in config options list. Do not fail is one is missing.

# v 1.6.0 (2022-09-09)
Changes in this release:
- Fix issue with "+" assignation and "?" in lexer
- Ensure that environment settings with an empty string as a default value are represented as ''

# v 1.5.0 (2022-01-24)
Changes in this release:
- Fix compatibility with recommonmark
- Fix compatibility with inmanta modules V2
- Added explicit project install for compatibility with latest inmanta-core

# v 1.4.0 (2021-04-15)
Changes in this release:
 - Correctly create an instance of the Project class.
 - Use stable inmanta-core api

# 1.3.0 (20-06-30)

## Change
 - Don't perform a full compile on documentation generation (#31)
 - Use * instead of \* to describe a relationship without upper bound.

# 1.2.0 (04-27-2020)

## Change
 - Handle empty description correctly.
 - Added namespace-files option to show-options directive

# 1.0.0

## Change
 - Options are no longer quoted by inmanta-sphinx but by inmanta config framework
