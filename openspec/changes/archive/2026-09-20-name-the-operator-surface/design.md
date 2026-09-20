# Design

## Why two capabilities and not one

They answer different questions and change for different reasons. `command-plan` is a contract between the
tool and the host: it is what every host-facing capability leans on, and it changes when the execution model
changes. `operator-interface` is the contract between the tool and the person: it changes when the CLI does.
Folding them together would make "previewed and confirmed" and "the menu takes 0" neighbours, which is how
the six restatements happened in the first place.

## Why now, and why no code changes

Every requirement here was written by reading the code and, where it renders, running it — not by reading
`docs/commands.md`. Where the code and a draft disagreed, the code won and the draft was rewritten: this is a
description of what the tool does today, so that the next change to any of it has something to be checked
against. A capability that is written from the documentation would lock in whatever has already drifted.

## What is deliberately left for later

The six capabilities that restate "previewed and confirmed" keep their sentences for now. Shortening each to
a reference to `command-plan` touches six files for no behavioural gain, and mixing it into the change that
introduces the capability would make both harder to review. The same applies to the three places that state
the ready-marker rule and the three that state `smtp 127.0.0.1:1025`.
