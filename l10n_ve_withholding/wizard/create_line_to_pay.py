from odoo import fields, models, api


class CreateLineToPay(models.TransientModel):
    _name = 'create.line.to.pay'
    _description = 'Create a wizard to display the information about to pay'

    currency_id = fields.Many2one('res.currency', string='Currency')
    date = fields.Date('Fecha')
    date_maturity = fields.Date('Fecha de vencimiento')
    move_id = fields.Many2one(
        'account.move',
        string='Asiento contable'
    )
    name = fields.Char('Etiqueta')
    ref = fields.Char('Referencia')
    account_id = fields.Many2one(
        'account.account',
        string='Cuenta'
    )
    journal_id = fields.Many2one(
        'account.journal',
        string='Diario'
    )
    vat_retention = fields.Selection([
        ('75', ' 75%'),
        ('100', '100%'),
    ],
        'Retención I.V.A',
        default='100'
    )

    line_type = fields.Selection([('debit', 'Débito'), ('credit', 'Crédito')], string='Tipo')
    balance = fields.Monetary(string='Importe', currency_field='currency_id')
    suggested_amount_residual = fields.Monetary(string='Importe Residual Sugerido', currency_field='currency_id')
    amount_residual = fields.Monetary(
        string='Importe Residual',
        currency_field='currency_id',
        compute='_get_amount_residual'
    )

    @api.onchange('vat_retention')
    @api.depends('vat_retention')
    def _get_amount_residual(self):
        for rec in self:
            rec.amount_residual = (int(self.vat_retention) / 100) * self.balance

    def get_islr_account(self):
        return self.env['account.journal'].search([('apply_islr', '=', True)], limit=1)

    def add_account_move_line(self):
        self.ensure_one()
        payment_group = self.env['account.payment.group'].browse(self._context.get('account_group_id', False))
        ret_account_journal = self.get_islr_account() or self.account_id
        account_move = self.create_journal_items(ret_account_journal.default_account_id.id)

        account_move.action_post()
        if payment_group:
            payment_group.to_pay_move_line_ids += account_move.line_ids.filtered(lambda l: l.debit == 0.0)

    def create_journal_items(self, ret_account_id):
        debit_vals = {
            'name': self.name or '/',
            'debit': abs(self.amount_residual),
            'credit': 0.0,
            'account_id': ret_account_id,
            'partner_id': self.move_id.partner_id.id,
            'balance': self.balance
        }
        credit_vals = {
            'name': self.name or '/',
            'debit': 0.0,
            'credit': abs(self.amount_residual),
            'account_id': self.account_id.id,
            'partner_id': self.move_id.partner_id.id,
            'balance': self.balance
        }
        vals = {
            'journal_id': self.journal_id.id,
            'date': self.date,
            'state': 'draft',
            'line_ids': [(0, 0, debit_vals), (0, 0, credit_vals)],
        }
        account_move = self.env['account.move'].create(vals)
        return account_move
