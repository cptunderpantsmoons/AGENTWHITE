```markdown
# AGENTWHITE Development Patterns

> Auto-generated skill from repository analysis

## Overview
This skill teaches you the core development patterns, coding conventions, and key workflows used in the AGENTWHITE repository—a Python backend application built with Flask. The repository emphasizes robust API security, owner-scoped access, conventional commit messages, and a clear separation of concerns between backend, frontend, and CI/CD logic. You'll learn how to contribute features, fix bugs, harden security, and maintain code quality according to established practices.

## Coding Conventions

- **File Naming:**  
  Use `snake_case` for all Python files.
  ```
  # Good
  routes/user_routes.py
  src/task_scheduler.py

  # Bad
  routes/UserRoutes.py
  src/taskScheduler.py
  ```

- **Import Style:**  
  Use relative imports within modules.
  ```python
  # Good
  from .utils import get_user

  # Bad
  import utils
  ```

- **Export Style:**  
  Use named exports; avoid wildcard imports.
  ```python
  # Good
  def my_function():
      pass

  __all__ = ['my_function']

  # Bad
  from module import *
  ```

- **Commit Messages:**  
  Follow [Conventional Commits](https://www.conventionalcommits.org/) with these prefixes:
    - `fix`: Bug fixes
    - `feat`: New features or enhancements
    - `ci`: CI/CD or workflow changes
    - `docs`: Documentation updates
    - `refactor`: Code restructuring without behavior change

  Example:
  ```
  fix(task_scheduler): handle timezone edge case in scheduling
  ```

## Workflows

### API Endpoint Owner Scope Hardening
**Trigger:** When you need to ensure API endpoints and logic are restricted to the resource owner.  
**Command:** `/harden-endpoint-owner-scope`

1. Update one or more `routes/*_routes.py` files to add or tighten owner checks.
   ```python
   # Example: Restricting access to the resource owner
   @app.route('/api/resource/<id>')
   @login_required
   def get_resource(id):
       resource = get_resource_by_id(id)
       if resource.owner_id != current_user.id:
           abort(403)
       return jsonify(resource.to_dict())
   ```
2. Update corresponding `src/*` files (e.g., `src/task_scheduler.py`, `src/chat_handler.py`) to propagate or enforce owner scoping.
3. Add or update tests in `tests/` to verify owner scoping and regression coverage.
   ```
   tests/test_task_owner_scope.py
   ```
4. Commit with a message like:
   ```
   fix(user_routes): enforce owner scoping for user data endpoints
   ```

---

### Bugfix with Regression Test
**Trigger:** When a bug is found and a regression test is needed.  
**Command:** `/bugfix-with-test`

1. Fix the bug in the relevant `src/` or `routes/` file.
   ```python
   # Example: Fixing a logic bug
   def calculate_total(items):
       return sum(item.price for item in items if item.available)
   ```
2. Add or update a test in `tests/` to cover the specific bug and its edge cases.
   ```
   tests/test_calculate_total.py
   ```
3. Document the fix in the commit message, referencing the test file.
   ```
   fix(calculate_total): handle unavailable items (see test_calculate_total.py)
   ```

---

### Security Hardening with Integration Tests
**Trigger:** When a security vulnerability or hardening opportunity is identified.  
**Command:** `/security-harden`

1. Update application or middleware code to address the security issue (e.g., CORS, SSRF, privilege checks).
   ```python
   # Example: Adding CORS headers
   from flask_cors import CORS
   CORS(app, resources={r"/api/*": {"origins": "https://trusted.domain"}})
   ```
2. Add or update integration tests in `tests/` to cover the security scenario.
   ```
   tests/test_cors_security.py
   ```
3. Document the security context and test coverage in the commit message.
   ```
   fix(cors): restrict origins for sensitive endpoints (see test_cors_security.py)
   ```

---

### Feature Addition or Enhancement with Tests
**Trigger:** When adding a new feature or enhancing an existing one.  
**Command:** `/add-feature`

1. Implement the feature in `src/` and/or `routes/` files.
   ```python
   # Example: New endpoint
   @app.route('/api/new_feature', methods=['POST'])
   def new_feature():
       # implementation
       pass
   ```
2. Update or create relevant `static/js/*` files if the UI is involved.
3. Add or update tests in `tests/` to cover new or changed behavior.
   ```
   tests/test_new_feature.py
   ```
4. Commit with a message like:
   ```
   feat(new_feature): add endpoint for new capability
   ```

---

### Frontend Bugfix or Enhancement
**Trigger:** When a UI bug or UX improvement is needed.  
**Command:** `/frontend-fix`

1. Update `static/js/*.js` and/or `static/style.css` to fix or enhance frontend behavior.
   ```js
   // Example: Fixing a button click handler
   document.getElementById('submit-btn').onclick = function() {
     // improved logic
   }
   ```
2. Optionally update `static/*.html` or `docs/index.html` for markup changes.
3. Document the UI/UX impact in the commit message.
   ```
   fix(ui): improve submit button accessibility
   ```

---

### CI or DevOps Workflow Update
**Trigger:** When CI/CD needs to be optimized or corrected for certain file patterns.  
**Command:** `/update-ci-workflow`

1. Update `.github/workflows/*.yml` or related CI/CD config files.
   ```yaml
   # Example: Skip tests for docs-only changes
   jobs:
     test:
       if: "!contains(github.event.head_commit.message, '[docs only]')"
   ```
2. Implement logic to skip or adjust test runs based on file patterns.
3. Document the workflow change in the commit message.
   ```
   ci(workflow): skip tests for documentation-only changes
   ```

## Testing Patterns

- **Test File Naming:**  
  Python test files follow `test_*.py` naming (e.g., `test_task_owner_scope.py`).
- **Test Location:**  
  All tests are located in the `tests/` directory.
- **Test Framework:**  
  The specific framework is unknown, but standard Python test conventions are followed.
- **Frontend Tests:**  
  JavaScript tests may use the `*.test.ts` pattern, though usage is limited.

**Example Python Test:**
```python
def test_owner_scope_enforced(client, user, resource):
    response = client.get(f'/api/resource/{resource.id}', headers={'Authorization': user.token})
    assert response.status_code == 200
    # Try as another user
    other_user = create_user()
    response = client.get(f'/api/resource/{resource.id}', headers={'Authorization': other_user.token})
    assert response.status_code == 403
```

## Commands

| Command                       | Purpose                                                        |
|-------------------------------|----------------------------------------------------------------|
| /harden-endpoint-owner-scope  | Harden API endpoints to enforce per-owner access controls       |
| /bugfix-with-test             | Fix a bug and add a regression test                            |
| /security-harden              | Apply security hardening and add integration tests             |
| /add-feature                  | Add a new feature or enhance an existing one with tests        |
| /frontend-fix                 | Fix or enhance frontend JavaScript, CSS, or HTML               |
| /update-ci-workflow           | Update CI/CD workflow files for optimized test running         |
```
