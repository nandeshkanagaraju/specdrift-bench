# semver specification

## Construction

- **R01** `Version.__init__` MUST raise `ValueError` when the major, minor or patch part is negative.

## Parsing

- **R02** `Version.parse` MUST raise `ValueError` for a string that does not follow the SemVer grammar.
- **R03** `Version.parse` MUST raise `TypeError` for an argument that is neither `str` nor `bytes`.
- **R04** `Version.parse` MUST set an absent minor or patch part to 0 when `optional_minor_and_patch` is true.
- **R05** `Version.parse` MUST reject a major part that has a leading zero.

## Comparison

- **R06** `Version.compare` MUST NOT take the build part into account.
- **R07** `Version.compare` MUST rank a version without a prerelease higher than the same version with one.
- **R08** `Version.compare` MUST compare numeric prerelease identifiers by their numeric value.

## Matching

- **R09** `Version.match` MUST treat an expression that starts with a digit as an equality test.
- **R10** `Version.match` MUST raise `ValueError` for an expression that has no operator and does not start with a digit.

## Bumping

- **R11** `Version.bump_major` MUST return a version with minor, patch, prerelease and build cleared.
- **R12** `Version.bump_patch` MUST increase the patch part by 1 and drop the prerelease and build parts.
- **R13** `Version.bump_prerelease` MUST give a version without a prerelease the prerelease `<token>.1`.
- **R14** `Version.bump_prerelease` MUST NOT change the patch part of a version without a prerelease unless `bump_when_empty` is true.

## Next version

- **R15** `Version.next_version` MUST raise `ValueError` for a part other than major, minor, patch or prerelease.
- **R16** `Version.next_version` MUST drop the prerelease and build parts when the part is `patch` and a prerelease exists.

## Compatibility

- **R17** `Version.is_compatible` MUST return `False` when the major parts differ.
- **R18** `Version.is_compatible` MUST return `False` when the other minor part is lower than the own minor part.

## Formatting and access

- **R19** `Version.__getitem__` MUST raise `IndexError` for a negative index.
- **R20** `Version.__str__` MUST format a version as `major.minor.patch`, followed by `-prerelease` and `+build` only when they exist.
