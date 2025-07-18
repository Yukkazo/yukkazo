# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import markupsafe

from odoo import models, fields, api
from odoo.exceptions import UserError
from odoo.tools.misc import formatLang, format_date, get_lang
from odoo.tools.translate import _
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT, html2plaintext, plaintext2html


class AccountFollowupReport(models.AbstractModel):
    _name = 'account.followup.report'
    _description = "Follow-up Report"

    # This report, while not an account.report per se, still uses (inherited) templates from account_reports
    main_table_header_template = 'account_followup.table_header_template_followup_report'

    filter_show_draft = False

    ####################################################
    # REPORT COMPUTATION - TEMPLATE RENDERING
    ####################################################

    def get_followup_report_html(self, options):
        """
        Return the html of the followup report, based on the report options.
        """
        template = 'account_followup.template_followup_report'
        render_values = self._get_followup_report_html_render_values(options)

        headers = [self._get_followup_report_columns_name()]
        lines = self._get_followup_report_lines(options)

        # Catch negative numbers when present
        for line in lines:
            for col in line['columns']:
                if self.env.company.currency_id.compare_amounts(col.get('no_format', 0.0), 0.0) == -1:
                    col['class'] = 'number color-red'

        render_values['lines'] = {'columns_header': headers, 'lines': lines}

        return self.env['ir.qweb']._render(template, render_values)

    def _get_followup_report_lines(self, options):
        """
        Compute and return the lines of the columns of the follow-ups report.
        """
        # Get date format for the lang
        partner = options.get('partner_id') and self.env['res.partner'].browse(options['partner_id']) or False
        if not partner:
            return []

        lang_code = partner.lang
        lines = []
        res = {}
        today = fields.Date.today()
        line_num = 0
        for l in partner.unreconciled_aml_ids.sorted().filtered(lambda aml: not aml.currency_id.is_zero(aml.amount_residual_currency)):
            if l.company_id == self.env.company and not l.blocked:
                currency = l.currency_id or l.company_id.currency_id
                if currency not in res:
                    res[currency] = []
                res[currency].append(l)
        for currency, aml_recs in res.items():
            total = 0
            total_issued = 0
            for aml in aml_recs:
                amount = aml.amount_residual_currency if aml.currency_id else aml.amount_residual
                invoice_date = {
                    'name': format_date(self.env, aml.move_id.invoice_date or aml.date, lang_code=lang_code),
                    'class': 'date',
                    'style': 'white-space:nowrap;text-align:center;',
                    'template': 'account_followup.cell_template_followup_report',
                }
                date_due = format_date(self.env, aml.date_maturity or aml.move_id.invoice_date or aml.date, lang_code=lang_code)
                total += not aml.blocked and amount or 0
                is_overdue = today > aml.date_maturity if aml.date_maturity else today > aml.date
                is_payment = aml.payment_id
                if is_overdue or is_payment:
                    total_issued += not aml.blocked and amount or 0
                date_due = {
                    'name': date_due, 'class': 'date',
                    'style': 'white-space:nowrap;text-align:center;',
                    'template': 'account_followup.cell_template_followup_report',
                }
                if is_overdue:
                    date_due['style'] += 'color: red;'
                if is_payment:
                    date_due = ''
                move_line_name = {
                    'name': self._followup_report_format_aml_name(aml.name, aml.move_id.ref),
                    'style': 'text-align:right; white-space:normal;',
                    'template': 'account_followup.cell_template_followup_report',
                }
                amount = {
                    'name': formatLang(self.env, amount, currency_obj=currency),
                    'style': 'text-align:right; white-space:normal;',
                    'template': 'account_followup.cell_template_followup_report',
                }
                line_num += 1
                invoice_origin = aml.move_id.invoice_origin or ''
                if len(invoice_origin) > 43:
                    invoice_origin = invoice_origin[:40] + '...'
                invoice_origin = {
                    'name': invoice_origin,
                    'style': 'text-align:center; white-space:normal;',
                    'template': 'account_followup.cell_template_followup_report',
                }
                #                   move_line_name,
                columns = [
                    invoice_date,
                    date_due,
                    invoice_origin,
                    amount,
                ]
                lines.append({
                    'id': aml.id,
                    'account_move': aml.move_id,
                    'name': aml.move_id.name,
                    'move_id': aml.move_id.id,
                    'type': is_payment and 'payment' or 'unreconciled_aml',
                    'unfoldable': False,
                    'columns': [isinstance(v, dict) and v or {'name': v, 'template': 'account_followup.cell_template_followup_report'} for v in columns],
                })
            total_due = formatLang(self.env, total, currency_obj=currency)
            line_num += 1

            cols = \
                [{
                    'name': v,
                    'template': 'account_followup.cell_template_followup_report',
                } for v in [''] * 3] + \
                [{
                    'name': v,
                    'style': 'text-align:right; white-space:normal;',
                    'template': 'account_followup.cell_template_followup_report',
                } for v in [total >= 0 and _('Total Due') or '', total_due]]

            lines.append({
                'id': line_num,
                'name': '',
                'class': 'total',
                'style': 'border-top-style: double',
                'unfoldable': False,
                'level': 3,
                'columns': cols,
            })
            if total_issued > 0:
                total_issued = formatLang(self.env, total_issued, currency_obj=currency)
                line_num += 1

                cols = \
                    [{
                        'name': v,
                        'template': 'account_followup.cell_template_followup_report',
                    } for v in [''] * 3] + \
                    [{
                        'name': v,
                        'style': 'text-align:right; white-space:normal;',
                        'template': 'account_followup.cell_template_followup_report',
                    } for v in [_('Total Overdue'), total_issued]]

                lines.append({
                    'id': line_num,
                    'name': '',
                    'class': 'total',
                    'unfoldable': False,
                    'level': 3,
                    'columns': cols,
                })
            # Add an empty line after the total to make a space between two currencies
            line_num += 1
            lines.append({
                'id': line_num,
                'name': '',
                'class': '',
                'style': 'border-bottom-style: none',
                'unfoldable': False,
                'level': 0,
                'columns': [{'template': 'account_followup.cell_template_followup_report'} for col in columns],
            })
        # Remove the last empty line
        if lines:
            lines.pop()
        return lines

    def _get_followup_report_html_render_values(self, options):
        # Needed for account_reports templates
        options['show_debug_column'] = False
        partner = self.env['res.partner'].browse(options['partner_id'])
        return {
            'partner': partner,
            'lang': partner.lang or get_lang(self.env).code,
            'invoice_address_id': self.env['res.partner'].browse(partner.address_get(['invoice'])['invoice']),
            'today': fields.date.today().strftime(DEFAULT_SERVER_DATE_FORMAT),
            'report_summary': self._get_main_body(options),
            'report': self,
            'report_title': _("Estado de Cuenta"),
            'report_company_name': self.env.company.name,
            'followup_report_email_subject': self._get_email_subject(options),
            'followup_line': options.get('followup_line_id', partner.followup_line_id),
            'options': options,
            'context': self.env.context,
            'model': self,
            'table_end': markupsafe.Markup('''
                </tbody></table>
                <div style="page-break-after: always"></div>
                <table class="o_account_reports_table table-hover">
            '''),
            'table_start': markupsafe.Markup('<tbody>'),
        }

    @api.model
    def _followup_report_format_aml_name(self, line_name, move_ref, move_name=None):
        """ Format the display of an account.move.line record. As its very costly to fetch the account.move.line
        records, only line_name, move_ref, move_name are passed as parameters to deal with sql-queries more easily.

        :param line_name:   The name of the account.move.line record.
        :param move_ref:    The reference of the account.move record.
        :param move_name:   The name of the account.move record.
        :return:            The formatted name of the account.move.line record.
        """
        names = []
        if move_name is not None and move_name != '/':
            names.append(move_name)
        if move_ref and move_ref != '/':
            names.append(move_ref)
        if line_name and line_name != move_name and line_name != '/':
            names.append(line_name)
        name = '-'.join(names)
        return name

    def _get_caret_options(self):
        # Method needed by the account_reports.main_template template, but unused for the followup report
        return {}

    ####################################################
    # DEFAULT BODY AND EMAIL SUBJECT
    ####################################################

    @api.model
    def _get_rendered_body(self, partner_id, template_src, default_body, **kwargs):
        """ Returns the body that can be rendered by the template_src, or if None, returns the default_body.
        kwargs can contain any keyword argument supported by the *_render_template* function
        """
        if template_src:
            return self.env['mail.composer.mixin'].sudo()._render_template(template_src, 'res.partner', [partner_id], **kwargs)[partner_id]

        return default_body

    @api.model
    def _get_sms_body(self, options):
        # Manual follow-up: return body from options
        if options.get('sms_body'):
            return options.get('sms_body')

        partner = self.env['res.partner'].browse(options.get('partner_id'))
        followup_line = options.get('followup_line', partner.followup_line_id)
        sms_template = options.get('sms_template') or followup_line.sms_template_id
        template_src = sms_template.body

        partner_followup_responsible_id = partner._get_followup_responsible()
        responsible_signature = html2plaintext(partner_followup_responsible_id.signature or partner_followup_responsible_id.name)
        default_body = _("Dear client, we kindly remind you that you still have unpaid invoices. Please check them and take appropriate action. %s", responsible_signature)

        return self._get_rendered_body(partner.id, template_src, default_body, post_process=True)

    @api.model
    def _get_email_from(self, options):
        partner = self.env['res.partner'].browse(options.get('partner_id'))
        # For manual followups, get the email_from from the selected template in the send & print wizard.
        if options.get('email_from'):
            followup_email_from = options['email_from']
        # For automatic followups, get it from mail template on the followup line.
        else:
            followup_line = options.get('followup_line') or partner.followup_line_id
            mail_template = options.get('mail_template') or followup_line.mail_template_id
            followup_email_from = mail_template.email_from
        # The _render_template() function formats the email content. It handles cases where the email_from value
        # is a template that needs evaluation. For instance, "{{ object._get_followup_responsible().email_formatted }}".
        return self.env['mail.composer.mixin'].sudo()._render_template(followup_email_from, 'res.partner', [partner.id])[partner.id] or None

    @api.model
    def _get_email_reply_to(self, options):
        partner = self.env['res.partner'].browse(options.get('partner_id'))
        followup_line = options.get('followup_line', partner.followup_line_id)
        mail_template = options.get('mail_template', followup_line.mail_template_id)
        # if template has no reply-to set, fall back to default reply-to, otherwise
        # it will be set to False and behave unexpectedly
        if mail_template.reply_to:
            followup_reply_to = mail_template.reply_to
        else:
            followup_reply_to = self._notify_get_reply_to()[False]
        return followup_reply_to

    @api.model
    def _get_main_body(self, options):
        # Manual follow-up: return body from options
        if options.get('body'):
            return options.get('body')

        partner = self.env['res.partner'].browse(options.get('partner_id'))
        followup_line = options.get('followup_line', partner.followup_line_id)
        mail_template = options.get('mail_template', followup_line.mail_template_id)
        template_src = None
        if mail_template:
            template_src = mail_template.with_context(lang=partner.lang or self.env.user.lang).body_html

        partner_followup_responsible_id = partner._get_followup_responsible()
        responsible_signature = partner_followup_responsible_id.signature or partner_followup_responsible_id.name
        self = self.with_context(lang=partner.lang or self.env.user.lang)
        default_body = _("""Dear %s,


Exception made if there was a mistake of ours, it seems that the following amount stays unpaid. Please, take appropriate measures in order to carry out this payment in the next 8 days.

Would your payment have been carried out after this mail was sent, please ignore this message. Do not hesitate to contact our accounting department.

Best Regards,

""", partner.name)

        default_body_html = plaintext2html(default_body) + responsible_signature  # responsible_signature is an html field
        return self._get_rendered_body(partner.id, template_src, default_body_html, engine='qweb', post_process=True)

    @api.model
    def _get_email_subject(self, options):
        # Manual follow-up: return body from options
        if options.get('email_subject'):
            return options.get('email_subject')

        partner = self.env['res.partner'].browse(options.get('partner_id'))
        followup_line = options.get('followup_line', partner.followup_line_id)
        mail_template = options.get('mail_template', followup_line.mail_template_id)
        template_src = None
        if mail_template:
            template_src = mail_template.with_context(lang=partner.lang or self.env.user.lang).subject

        partner_name = partner.name
        company_name = self.env.company.name
        self = self.with_context(lang=partner.lang or self.env.user.lang)
        default_body = _("%s Payment Reminder - %s", company_name, partner_name)

        return self._get_rendered_body(partner.id, template_src, default_body, post_process=True)

    ####################################################
    # REPORT DATA
    ####################################################

    def _get_followup_report_columns_name(self):
        """
        Return the name of the columns of the follow-ups report
        """
        return [
            {'name': _('Reference'), 'style': 'text-align:center; white-space:nowrap; width:15%;'},
            {'name': _('Date'), 'class': 'date', 'style': 'text-align:center; white-space:nowrap; width:15%;'},
            {'name': _('Due Date'), 'class': 'date', 'style': 'text-align:center; white-space:nowrap; width:15%;'},
            {'name': _('Origin'), 'style': 'text-align:center; white-space:nowrap; width:40%;'},
            {'name': _('Total Due'), 'class': 'number o_price_total', 'style': 'text-align:right; white-space:nowrap; width:15%;'},
        ]

    ####################################################
    # EXPORT  {'name': _('Communication'), 'style': 'text-align:right; white-space:nowrap;'},
    ####################################################

    @api.model
    def _send_sms(self, options):
        """
        Send by SMS the followup to the customer
        """
        partner = self.env['res.partner'].browse(options.get('partner_id'))
        followup_contacts = partner._get_all_followup_contacts() or partner
        sent_at_least_once = False
        for to_send_partner in followup_contacts:
            sms_number = to_send_partner.mobile or to_send_partner.phone
            if sms_number:
                sms_body = self.with_context(lang=partner.lang or self.env.user.lang)._get_sms_body(options)
                partner._message_sms(
                    body=sms_body,
                    partner_ids=partner.ids,
                    sms_pid_to_number={partner.id: sms_number},
                )
                sent_at_least_once = True
        if not sent_at_least_once:
            raise UserError(_("You are trying to send an SMS, but no follow-up contact has any mobile/phone number set for customer '%s'", partner.name))

    @api.model
    def _send_email(self, options):
        """
        Send by email the followup to the customer's followup contacts
        """
        partner = self.env['res.partner'].browse(options.get('partner_id'))
        followup_contacts = partner._get_all_followup_contacts() or partner
        followup_recipients = options.get('email_recipient_ids', followup_contacts)
        sent_at_least_once = False
        for to_send_partner in followup_recipients:
            email = to_send_partner.email
            if email and email.strip():
                self = self.with_context(lang=partner.lang or self.env.user.lang)
                body_html = self.with_context(mail=True).get_followup_report_html(options)

                attachment_ids = options.get('attachment_ids', partner._get_invoices_to_print(options).message_main_attachment_id.ids)
                # If the follow-up was executed manually, the author_id will be set to the ID of the current logged-in user.
                # Otherwise, if the follow-up is automatic, the author_id will be the followup responsible or OdooBot.
                author_id = options.get('author_id', partner._get_followup_responsible().partner_id.id)

                partner.with_context(mail_post_autofollow=True, mail_notify_author=True, lang=partner.lang or self.env.user.lang).message_post(
                    partner_ids=[to_send_partner.id],
                    author_id=author_id,
                    email_from=self._get_email_from(options),
                    body=body_html,
                    subject=self._get_email_subject(options),
                    reply_to=self._get_email_reply_to(options),
                    subtype_id=self.env.ref('mail.mt_note').id,
                    model_description=_('payment reminder'),
                    email_layout_xmlid='mail.mail_notification_light',
                    attachment_ids=attachment_ids,
                )
                sent_at_least_once = True
        if not sent_at_least_once:
            raise UserError(_("You are trying to send an Email, but no follow-up contact has any email address set for customer '%s'", partner.name))

    @api.model
    def _print_followup_letter(self, partner, options=None):
        """Generate the followup letter for the given partner.
        The letter is saved as ir.attachment and linked in the chatter.

        Returns a client action downloading this letter and closing the wizard.
        """
        action = self.env.ref('account_followup.action_report_followup')
        tz_date_str = format_date(self.env, fields.Date.today(), lang_code=self.env.user.lang or get_lang(self.env).code)
        #to avoid having dots in the name of the file.
        tz_date_str = tz_date_str.replace('.', '-')
        followup_letter_name = _("Estado de Cuenta %s - %s", partner.display_name, tz_date_str)
        followup_letter = action.with_context(lang=partner.lang or self.env.user.lang)._render_qweb_pdf('account_followup.report_followup_print_all', partner.id, data={'options': options or {}})[0]
        attachment = self.env['ir.attachment'].create({
            'name': followup_letter_name,
            'raw': followup_letter,
            'res_id': partner.id,
            'res_model': 'res.partner',
            'type': 'binary',
            'mimetype': 'application/pdf',
        })
        partner.message_post(body=_('Follow-up letter generated'), attachment_ids=[attachment.id])
        return {
            'type': 'ir.actions.client',
            'tag': 'close_followup_wizard',
            'params': {
                'url': '/web/content/%s?download=1' % attachment.id,
            }
        }
