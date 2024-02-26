from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)

class AccountPayment(models.Model):
    _inherit = "account.payment"
                
    def get_iva_retention(self):
        type_tax = self.tax_withholding_id.name
        if type(type_tax) == str and 'iva' in type_tax.lower():
            return '16%'
        elif type(type_tax) == str and'islr' in type_tax.lower():
            retained_percentage = (self.computed_withholding_amount * 100) / self.total_amount
            return  f'{retained_percentage:.2f}%'
        else:
            return f'{self.tax_withholding_id.description}' if type_tax else '0.00'