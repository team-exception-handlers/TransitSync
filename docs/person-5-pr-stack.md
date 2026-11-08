# Person 5 PR stack

The completed source branch `feat/61-person-5-coordinated-strategies` remains
unchanged at `7777516`. Four cumulative review branches partition its contents.
Each PR targets the preceding branch; the first targets main. Publish only after
the user approves the exact title and body. Merge into main in dependency order,
retargeting each next PR and running CI before merging. Python CI currently only
runs automatically for PRs targeting main. No CI configuration changes are needed.

Production Python files must match the completed source branch exactly once the
stack is complete. Tests are split by dependency, preserving every original
test function and assertion. Stage-specific validation is recorded below.

## Review limits

Count source additions relative to each immediate base; tests and Markdown are
excluded. At most 250 requires one reviewer (two preferred); 251–400 requires
two. Every stage must remain at or below 400. Keep AI file headers, AI_USAGE.md
and PR declarations consistent. Merge with normal merge commits, not squashes.

## Local Design Patterns wiki draft

### Value Objects and Builder: future observations (#61)

Frozen FutureVisit values extend the existing ObservationBuilder and Strategy
pipeline without exposing mutable trains. The train component remains the sole
movement-state owner; the existing prediction layer perturbs copied forecasts.
This avoids a parallel mutable simulation. The existing oversized train module
retains its documented technical exception. No external library is introduced.

## Stage 1: Future-visit observations

Freeze forward visits, retain current holds and return recovery, and pass future forecasts through the existing prediction-error layer. Existing strategy selection is unchanged.

Files: planning.py, interface.py, observation_builder.py, prediction_error.py, decision.py and simulator/trains/train_component.py; rolling_helpers.py, test_planning_observation.py and test_planning_settings.py.

Validation: 1415 passed, one existing xfail (#192). Ruff lint, formatting,
extended clean-code checks, simulator compilation and whitespace checks passed.
Review size: 234 source additions; one reviewer required, two preferred.
