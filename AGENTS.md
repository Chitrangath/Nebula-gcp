# Agent Instructions

## Skill Usage Protocol

Before starting each phase of work, inspect all repository-installed skills and use every skill relevant to that phase. Record which skills were discovered, which were used, and why.

### Installed Skills Inventory

| Skill | Source | Phase Applicability |
|---|---|---|
| solidity-foundry-security | repo | Phase 1 (Smart Contracts) |
| tdd | mattpocock/skills | All phases (test-first) |
| domain-modeling | mattpocock/skills | All phases (vocabulary) |
| code-review | mattpocock/skills | All phases (review) |
| diagnosing-bugs | mattpocock/skills | Bug fixing |
| research | mattpocock/skills | Investigation |
| codebase-design | mattpocock/skills | Architecture |
| grill-with-docs | mattpocock/skills | Planning |
| improve-codebase-architecture | mattpocock/skills | Refactoring |
| handoff | mattpocock/skills | Session transitions |
| ask-matt | mattpocock/skills | Skill routing |
| setup-matt-pocock-skills | mattpocock/skills | Repo setup |
| teach | mattpocock/skills | Learning |
| wizard | mattpocock/skills | Human-in-the-loop |

### Phase-Specific Skill Rules

#### Phase 1: Smart Contracts (Solidity/Foundry)
- **Primary**: `solidity-foundry-security` — mandatory for all contract design, implementation, testing, and review
- **Supporting**: `tdd` — test-first approach for Foundry tests
- **Supporting**: `domain-modeling` — ensure contract domain matches CONTEXT.md
- **Review**: `code-review` — review implementation against PRD v3.1

#### Phase 2: Backend Infrastructure (Python/FastAPI)
- **Primary**: `tdd` — test-first for API endpoints and services
- **Supporting**: `domain-modeling` — backend domain vocabulary
- **Review**: `code-review` — review against PRD v3.1

#### Phase 3: Backend Services (Python)
- **Primary**: `tdd` — test-first for blockchain integration, proof verifier
- **Supporting**: `domain-modeling` — service domain vocabulary
- **Supporting**: `diagnosing-bugs` — if integration issues arise
- **Review**: `code-review` — review against PRD v3.1

#### Phase 4: Frontend (React/TypeScript)
- **Primary**: Matt Pocock skills are **mandatory** for:
  - TypeScript work
  - React components
  - Next.js pages
  - Frontend architecture
  - Type design
  - Validation
  - TypeScript testing
- **Supporting**: `tdd` — test-first for components
- **Supporting**: `domain-modeling` — UI domain vocabulary
- **Review**: `code-review` — review against PRD v3.1

#### Phase 5: Worker (Python)
- **Primary**: `tdd` — test-first for Merkle, EIP-712, execution
- **Supporting**: `domain-modeling` — worker domain vocabulary
- **Review**: `code-review` — review against PRD v3.1

#### Phase 6: Integration & Testing
- **Primary**: `diagnosing-bugs` — for integration issues
- **Supporting**: `tdd` — integration tests
- **Review**: `code-review` — full system review

#### Phase 7: Deployment
- **Supporting**: `wizard` — for human-only deployment steps
- **Review**: `code-review` — deployment script review

### Matt Pocock Skills Mandate

Matt Pocock skills (TypeScript, React, Next.js, frontend architecture, type design, validation, TypeScript testing) are **mandatory** for:
- All TypeScript code
- All React components
- All Next.js pages
- Frontend architecture decisions
- Type design and validation
- TypeScript test writing

Matt Pocock skills are **NOT** forced onto:
- Solidity/Foundry work (use `solidity-foundry-security` instead)
- Python/FastAPI work (use `tdd` and `domain-modeling` instead)
- Infrastructure/deployment work

### Skill Discovery and Recording

At the start of each phase, the agent must:

1. List all 14 installed skills
2. Identify which are relevant to the current phase
3. Justify why each selected skill is relevant
4. Apply each selected skill's instructions completely
5. Record the skill usage in the phase completion report

Example recording format:
```
## Phase X Skill Usage

### Discovered Skills
- solidity-foundry-security, tdd, domain-modeling, code-review, ...

### Applied Skills
1. **solidity-foundry-security**: Applied threat modeling, secure patterns, invariant testing
2. **tdd**: Applied red-green loop for test writing
3. **domain-modeling**: Ensured contract domain matches CONTEXT.md

### Not Applied (with reason)
- ask-matt: Meta-routing skill, not needed for implementation phase
- handoff: No session transition needed
```

## Development Standards

### Smart Contracts
- Follow `solidity-foundry-security` skill completely
- Target >=95% meaningful test coverage
- Run `forge build`, `forge test`, `forge test --gas-report`, `forge snapshot`
- Threat model before implementation
- Write invariant tests for critical properties

### Backend (Python)
- Follow `tdd` skill for test-first development
- Use type hints consistently
- Write docstrings for public interfaces
- Run type checker and linter before completion

### Frontend (TypeScript/React)
- Follow Matt Pocock skills completely
- Use proper TypeScript types
- Follow React best practices
- Write component tests

### General
- Read CONTEXT.md for domain vocabulary
- Follow existing code conventions
- Never commit secrets
- Run all verification commands before declaring work complete

Skills provide specialized instructions and workflows for specific tasks.
Use the skill tool to load a skill when a task matches its description.
