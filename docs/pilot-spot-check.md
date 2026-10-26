# Pilot spot-check sheet (you fill this in)

Generator: Claude (interactive session), acting as the model for prompts A and B exactly as written in `docs/rule-extraction-prompt.md`. The three libraries are `python-semver`, `cachetools` and `voluptuous`, cloned at the commits recorded in `data/repos_verified.csv`.

This is the human gate from section 7 of the prompt design. It cannot be done by the model that wrote the rules. Tick one box per question. To proceed you need **at least 90% of rules** and **at least 85% of oracles** passing every question.

## A. Rules (18 drawn at random, seed 17, from 57)

For each: (1) is it true of the library? (2) is it observable behaviour, not an accident of the implementation? (3) is it one requirement a test could decide?

| # | Library | Rule | Grounding | Cited line | True | Observable | One requirement |
|---|---|---|---|---|---|---|---|
| 1 | cachetools R04 | `Cache.__setitem__` MUST evict items until the new value fits within `maxsize`. | code | `while self.__currsize + diffsize > maxsize:` | [ ] | [ ] | [ ] |
| 2 | cachetools R05 | `Cache.pop` MUST raise `KeyError` for a missing key when no default is given. | code | `elif default is self.__marker:` | [ ] | [ ] | [ ] |
| 3 | cachetools R07 | `Cache.clear` MUST reset `currsize` to 0. | code | `self.__currsize = 0` | [ ] | [ ] | [ ] |
| 4 | cachetools R14 | `TTLCache.__getitem__` MUST raise `KeyError` for an item whose expiry time has been reached. | code | `expired = not (self.timer() < link.expires)` | [ ] | [ ] | [ ] |
| 5 | cachetools R15 | `TTLCache.expire` MUST return the expired `(key, value)` pairs and remove them from the cache. | documented | `expired.append((curr.key, cache_getitem(self, curr.key)))` | [ ] | [ ] | [ ] |
| 6 | semver R02 | `Version.parse` MUST raise `ValueError` for a string that does not follow the SemVer grammar. | documented | `raise ValueError(f"{version} is not valid SemVer string")` | [ ] | [ ] | [ ] |
| 7 | semver R08 | `Version.compare` MUST compare numeric prerelease identifiers by their numeric value. | code | `return (0, len(normalized), normalized)` | [ ] | [ ] | [ ] |
| 8 | semver R12 | `Version.bump_patch` MUST increase the patch part by 1 and drop the prerelease and build parts. | documented | `return cls(self._major, self._minor, self._patch + 1)` | [ ] | [ ] | [ ] |
| 9 | semver R16 | `Version.next_version` MUST drop the prerelease and build parts when the part is `patch` and a prerelease exists. | code | `return version.replace(prerelease=None, build=None)` | [ ] | [ ] | [ ] |
| 10 | semver R18 | `Version.is_compatible` MUST return `False` when the other minor part is lower than the own minor part. | documented | `and (other.minor >= self.minor)` | [ ] | [ ] | [ ] |
| 11 | semver R19 | `Version.__getitem__` MUST raise `IndexError` for a negative index. | documented | `raise IndexError("Version index cannot be negative")` | [ ] | [ ] | [ ] |
| 12 | semver R20 | `Version.__str__` MUST format a version as `major.minor.patch`, followed by `-prerelease` and `+build` only when they exist. | documented | `version = "%d.%d.%d" % (self.major, self.minor, self.patch)` | [ ] | [ ] | [ ] |
| 13 | voluptuous R04 | `Range.__call__` MUST reject a value equal to `max` when `max_included` is false. | documented | `if self.max is not None and not v < self.max:` | [ ] | [ ] | [ ] |
| 14 | voluptuous R07 | `Clamp.__call__` MUST return `max` for a value above `max`. | documented | `if self.max is not None and v > self.max:` | [ ] | [ ] | [ ] |
| 15 | voluptuous R10 | `Boolean` MUST return `True` for the strings `1`, `true`, `yes`, `on` and `enable`, ignoring case. | documented | `if v in ('1', 'true', 'yes', 'on', 'enable'):` | [ ] | [ ] | [ ] |
| 16 | voluptuous R11 | `Boolean` MUST return `False` for the strings `0`, `false`, `no`, `off` and `disable`, ignoring case. | documented | `if v in ('0', 'false', 'no', 'off', 'disable'):` | [ ] | [ ] | [ ] |
| 17 | voluptuous R13 | `IsFalse` MUST raise `FalseInvalid` for a value that is true in the Python sense. | documented | `@message('value was not false', cls=FalseInvalid)` | [ ] | [ ] | [ ] |
| 18 | voluptuous R17 | `Match.__call__` MUST match the pattern at the start of the string only. | code | `match = self.pattern.match(v)` | [ ] | [ ] | [ ] |

## B. Oracles (8 of the rules above)

For each: (4) does it test the rule and nothing else? (5) does it pass only because the library is right, not because it encodes a bug? Read the file listed, in `data/pilot/<library>/oracles/`; each is under 25 lines. The rules, their cited lines and their prompts are in `data/pilot/<library>/`.

| # | Library | Oracle file | Tests only the rule | Does not encode a bug |
|---|---|---|---|---|
| 1 | semver R16 | `oracles/test_r16.py` | [ ] | [ ] |
| 2 | voluptuous R13 | `oracles/test_r13.py` | [ ] | [ ] |
| 3 | semver R19 | `oracles/test_r19.py` | [ ] | [ ] |
| 4 | voluptuous R11 | `oracles/test_r11.py` | [ ] | [ ] |
| 5 | voluptuous R07 | `oracles/test_r07.py` | [ ] | [ ] |
| 6 | voluptuous R10 | `oracles/test_r10.py` | [ ] | [ ] |
| 7 | semver R20 | `oracles/test_r20.py` | [ ] | [ ] |
| 8 | semver R08 | `oracles/test_r08.py` | [ ] | [ ] |

## Scoring

Rules passing all three questions: ____ / 18 (17 needed for 90%).  Oracles passing both: ____ / 8 (7 needed for 85%).

If either threshold is missed, note which items failed and why. The prompt is then changed and the pilot repeated before anything is scaled.
