"""Decimal money calculations shared by validation and Word export."""
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from ratings import PRIORITY_OPTIONS, LEGACY_COST_PRIORITIES

FIELDS=['description','quantity','unit','rate','priority']
def amount(row):
    if not str(row.get('quantity','')).strip() or not str(row.get('rate','')).strip():return None
    return (Decimal(row['quantity'])*Decimal(row['rate'])).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP)

def validate_rows(rows):
    if not isinstance(rows,list) or len(rows)>500:raise ValueError('费用表最多 500 行')
    for row in rows:
        if not isinstance(row,dict):raise ValueError('费用表格式不正确')
        for key in FIELDS:
            value=row.setdefault(key,'')
            if not isinstance(value,str) or len(value)>(5000 if key=='description' else 100):raise ValueError('费用表内容过长')
        for key in ['quantity','rate']:
            value=row[key].strip()
            if value:
                if not re.fullmatch(r'(?:[0-9]+(?:\.[0-9]{0,6})?|\.[0-9]{1,6})',value):raise ValueError('数量和单价请使用普通非负数字，最多六位小数')
                try:number=Decimal(value)
                except InvalidOperation:raise ValueError('数量和单价必须是有效数字')
                if not number.is_finite() or number<0 or number>Decimal('1000000000'):raise ValueError('数量和单价须在 0 至 1000000000 之间')
                if number.as_tuple().exponent < -6:raise ValueError('数量和单价最多六位小数')
                row[key]=str(number)
        if row['priority'] not in ['', *PRIORITY_OPTIONS, *LEGACY_COST_PRIORITIES]:raise ValueError('费用优先级不正确')
