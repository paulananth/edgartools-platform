"""The rows the SEC submissions contracts read: each field as filed, else none,
a flag that is not one false, and the capture's run facts from the context."""

COMPANY_FIELDS = ('entity_name', 'entity_type', 'sic', 'sic_description', 'state_of_incorporation',
                  'state_of_incorporation_desc', 'fiscal_year_end', 'ein', 'description', 'category')
FILING_FIELDS = ('form', 'filing_date', 'report_date', 'acceptance_datetime', 'act', 'file_number', 'film_number',
                 'items', 'size', 'primary_document', 'primary_doc_desc')


def run_facts(context):
    return {'cik': context['cik'], 'sync_run_id': context['sync_run_id'],
            'raw_object_id': context['raw_object_id'], 'load_mode': context['load_mode']}


def company_row(context, **filed):
    return {**run_facts(context), **dict.fromkeys(COMPANY_FIELDS), 'last_sync_run_id': context['sync_run_id'],
            'last_synced_at': context['last_synced_at'], **filed}


def filing_row(accession, context, **filed):
    return {'accession_number': accession, **run_facts(context), **dict.fromkeys(FILING_FIELDS),
            'is_xbrl': False, 'is_inline_xbrl': False, **filed}
