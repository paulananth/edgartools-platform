# Capability gap: the data-platform route is not executable

Type: task
Status: open
Priority: P0
Blocked by: none
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)

## Question

Where is the function that takes a source's configuration and retained evidence and returns one next action and its owner?

## Evidence

Ticket 05's three approved scenarios need that function. The route exists only as text in [Start here](../../../skills/data-platform/SKILL.md#start-here-route-the-work) and [Resume](../../../skills/data-platform/RESUME.md). No module accepts invented configuration and returns Data Onboarding, Data Operations, Refining Rules, or the first unfinished owner.

A test that rereads those files would be the static-text proof ticket 05 forbids. Adding a router here would be new runtime code, which that ticket also forbids.

## Required behavior

One generic function, shared by every source. Inputs are invented configuration and retained artifacts: rules file present or absent, delivery changed or not, live-rule change or repeat run, and a Resume record whose hashes match or differ. Output is one owner and one next action. A completed phase whose recorded hashes match is not selected again.
