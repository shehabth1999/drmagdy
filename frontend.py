"""
Frontend permission config for the drmagdy instance.

This is the POLICY file for the (generic) frontend-permission mechanism that
lives in base (``modules/base/utils/frontend_config.py``). Base only provides the
mechanism; the actual rules live here, in this client module.

Activate it by pointing the ``FRONTEND_CONFIG_FILE`` env var at this file
(absolute path, since drmagdy lives outside the main repo):

    FRONTEND_CONFIG_FILE=E:/genie-erp/projects/drmagdy/frontend.py

How it works
------------
* This object is shared to the React frontend on every request (via the Inertia
  middleware) and gates UI affordances like the import / export buttons and
  profile editing. It also backs server-side enforcement on those endpoints.
* It applies to ALL non-superuser users the same way. Superusers bypass it and
  always get every capability.
* Only list what you want to DENY. Anything omitted defaults to ``True``, so
  leaving this file mostly empty == everything allowed.

Structure
---------
* Top level = GLOBAL switches (non-model capabilities + the default for models
  not listed): ``can_export``, ``can_import``, ``can_edit_profile``.
* ``models`` = PER-MODEL overrides. Key it by the model name (e.g. ``ticket``,
  ``lead``) or the app label (e.g. ``crm``), and give each one its own
  ``{"export": bool, "import": bool}``. A model entry overrides the global
  switch for that model only.

Lookup precedence for a model action: ``models[<app.model>]`` ->
``models[<model>]`` -> ``models[<app>]`` -> global ``can_<action>`` -> ``True``.
"""

FRONTEND_CONFIG = {
    # ----- Global switches (also the default for models not in `models`) -----
    # TEST: deny Export AND Import for ALL non-superusers, on every model.
    "can_export": False,
    "can_import": False,
    "can_edit_profile": False,

    # No per-model overrides — an entry with export/import True would beat the
    # global switch above and re-enable it for that model, so keep this empty
    # while testing the global deny.
    "models": {
        # "ticket": {"export": True, "import": True},
    },
}
