# ADR-0001: Modular control, execution, data, agent, and tool planes

- Status: Accepted
- Date: 2026-08-11

## Context

The eventual agent spans user interfaces, autonomous planning, LLM routing,
workers, memory, queues, browsers, and external tools. A monolithic container
would couple lifecycle, privileges, persistence, and failure domains.

## Decision

Separate control API, workers, PostgreSQL, Redis, optional Hermes, optional
OmniRoute, and future MCP gateway. Control plane owns policy/state transitions;
workers own allowlisted execution; PostgreSQL owns durable state; Redis owns
transient delivery.

## Alternatives

- One giant container: simpler first boot, poor security/upgrade/recovery.
- Kubernetes microservices: strong orchestration, unjustified single-VPS cost.
- Serverless managed services: lower operations, conflicts with self-hosted goal.

## Consequences

Compose and health dependencies are more detailed, but services can upgrade,
restart, back up, and receive privileges independently. Boundaries support a
future orchestration migration without requiring it now.

