MediExplain+ original runtime data was not included in the files uploaded for this integration.

To restore your existing consultations/recordings exactly, copy the CONTENTS of your original backend/data folder into this folder before running the final project. In particular this may include:
- mediexplain.db
- uploads/ consultation recordings, prescription images and generated PDFs
- model_cache/ if you want to reuse locally cached model assets

Do not replace backend/app, backend/scripts, backend/tests or backend/alembic with older copies. The final integration preserves the uploaded initial source pipeline and adds migration 0004 for assistant/support functionality.

If no old data is copied, setup_macos.sh will create/migrate a fresh database and seed demo accounts.
