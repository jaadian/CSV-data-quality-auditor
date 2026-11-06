# Learning log

Fill this in yourself, in your own words. Short and honest beats polished. An interviewer will ask about exactly these things.

For each entry: what happened, how you noticed, what you changed, what you would do differently.

## Bugs found while testing on real data

These were found by running the ten datasets. For each one, reproduce it yourself first (`git stash` the fix, run the regression test, watch it fail), then write the entry.

### Missing values in optional columns raised no issue
- Dataset: Titanic (Cabin 77% empty, zero issues)
- Test: `test_optional_column_missing_values_raise_issue`
- What I learned:

### Mixed int/float column inferred as integer
- Dataset: Titanic `Age`
- Test: `test_mixed_int_and_float_column_inferred_as_float`
- What I learned:

### Blank header stopped the run
- Dataset: Ames housing (pandas index column)
- Test: `test_blank_headers_renamed_and_flagged`
- What I learned:

### Score printed 100.0 with errors present
- Dataset: Earthquakes
- Test: `test_score_below_100_when_any_issue_exists`
- What I learned:

### Cross-column rule compared text silently
- Test: `test_cross_column_uncomparable_values_are_reported`
- What I learned:

### Range messages leaked masked values
- Test: `test_range_violation_message_respects_masking`
- What I learned:

### Recommendation claimed validation failures with no rules broken
- Dataset: Titanic HTML report
- Test: `test_validation_recommendation_only_for_rule_violations`
- What I learned:

## Things I would explain differently now

-

## What I would build next

-
