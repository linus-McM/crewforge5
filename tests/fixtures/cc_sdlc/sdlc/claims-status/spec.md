# Spec: Claims status
From: intent.md (2026-09-20). Status: accepted. Risk: medium.

## Requirements
1. R1 The portal shows a claim's status from the claims API.

## Design
A read-only `status(claim_id)` client and one portal view.

## Concerns
none

## Open questions
none

## Proof
tests/test_status.py
