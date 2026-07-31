Authentication & User Management
=================================

The web UI and its API guard everything except a set of read-only pages
behind a session cookie. Accounts are either **local** (username +
password, stored in the API's SQLite database) or **SSO** (provisioned via
an OIDC provider). This page covers first-time setup, day-to-day sign-in,
roles, and managing users.

Roles
-----

There are two roles:

- **user** - can acquire/release places, create places and reservations,
  open a place's console, and view/play back recordings.
- **admin** - everything a **user** can do, plus managing accounts on the
  :ref:`web-ui-admin-users` page.

Route access falls into three tiers:

.. list-table::
   :header-rows: 1

   * - Access
     - Pages
   * - Public (no login)
     - Dashboard, Places, Resources, Statistics, Event Log, Topology, Help,
       exporter detail pages
   * - Signed-in user
     - Reservations, place creation wizard, place detail, console, recordings
       and playback
   * - Admin only
     - :ref:`web-ui-admin-users` (``/admin/users``)

The REST API enforces the same rules server-side (``current_user`` /
``require_admin`` dependencies in ``coordinator/api/app/auth/dependencies.py``),
so the frontend checks are a convenience, not the security boundary.

First-time setup: bootstrapping the initial admin
---------------------------------------------------

There is no default account or password. On startup, if the user table is
empty, the API generates a one-time bootstrap token and writes it to its
own logs:

.. code-block:: bash

   docker compose -f coordinator/docker-compose.yml logs api | grep -A2 "FIRST RUN"

.. code-block:: text

   FIRST RUN: bootstrap token (use POST /api/auth/bootstrap):
       <random-token>

Use the token to create the first admin account:

.. code-block:: bash

   curl -X POST http://localhost:8000/api/auth/bootstrap \
     -H "Content-Type: application/json" \
     -d '{"token": "<token-from-logs>", "username": "admin", "password": "<choose-a-password>"}'

This creates a ``role="admin"`` user and immediately invalidates the token
(the endpoint returns ``410 Gone`` once any user exists, and ``403`` for a
wrong token). If you restart the ``api`` container before bootstrapping, a
fresh token is generated as long as no user has been created yet. If you
lose the token after users already exist, there is no way to re-bootstrap —
log in as an existing admin instead, or reset the API's database volume to
start over.

Signing in
----------

Go to ``/login`` on the web dashboard. Local accounts sign in with
username and password. If OIDC is configured (see below), a "Continue with
SSO" button is also shown.

A successful login sets an ``httponly`` session cookie (name and lifetime
are configurable, see :ref:`web-ui-session-config`). ``GET /api/auth/me``
returns the current user; ``POST /api/auth/logout`` clears the session.

.. _web-ui-admin-users:

Managing users
--------------

Admins manage accounts from **Admin -> Users** (``/admin/users``):

- **Add user**: create a local account with a username, password, and role
- **Role**: promote/demote between ``user`` and ``admin`` via an inline selector
- **Enable/disable**: disabling blocks login without deleting the account
- **Reset password**: set a new password for a local account
- **Delete**: remove the account
- Each row shows whether the account authenticates locally, via SSO, or both

These actions map directly to the ``/api/users`` endpoints listed in
:doc:`coordinator`.

Single sign-on (OIDC)
----------------------

SSO is optional and disabled by default. Set these environment variables
on the ``api`` service (see ``coordinator/docker-compose.yml``) to enable it:

.. list-table::
   :header-rows: 1

   * - Variable
     - Purpose
     - Default
   * - ``LG_OIDC_ISSUER_URL``
     - OIDC provider issuer URL; setting this enables SSO
     - unset (disabled)
   * - ``LG_OIDC_CLIENT_ID``
     - OIDC client ID
     - unset
   * - ``LG_OIDC_CLIENT_SECRET``
     - OIDC client secret
     - unset
   * - ``LG_OIDC_AUTO_PROVISION``
     - Automatically create a local user record (role ``user``) the first
       time someone signs in via SSO
     - ``false``

When ``LG_OIDC_AUTO_PROVISION`` is disabled, an SSO login for an unknown
subject is rejected with "ask an admin to create your account" — an admin
must create a matching account (any password) first. New SSO
auto-provisioned accounts always start with role ``user``; an existing
admin must promote them if needed.

.. _web-ui-session-config:

Session configuration
----------------------

.. list-table::
   :header-rows: 1

   * - Variable
     - Purpose
     - Default
   * - ``LG_SESSION_TTL_HOURS``
     - Hours before a session expires and re-login is required
     - ``24``
   * - ``LG_SESSION_COOKIE_NAME``
     - Name of the session cookie
     - ``lg_session``
   * - ``LG_SESSION_COOKIE_SECURE``
     - Mark the cookie ``Secure`` (HTTPS only)
     - ``false``

If you put the stack behind HTTPS (a reverse proxy, ingress, etc.), set
``LG_SESSION_COOKIE_SECURE=true`` so session cookies aren't sent over plain
HTTP.
