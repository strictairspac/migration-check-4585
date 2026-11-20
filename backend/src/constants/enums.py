ROLES=('admin','operator','viewer')
STATUSES=('queued','running','completed','failed','cancelled')
TYPES={'sample_code':'text','test_name':'text','result_value':'decimal','unit':'text','measured_at':'datetime'}
# 逐行拒绝原因：缺规则/非有限值/越界/超精度/原单位不允许，以及既有的结构类原因
REJECT_REASONS=('unit_rule_missing','source_unit_not_allowed','invalid_decimal','value_out_of_range','precision_loss','null_required','missing_column','text_too_long','invalid_datetime','duplicate_natural_key','invalid_row')
REJECT_REASON_LABELS={
 'unit_rule_missing':'缺少换算规则',
 'source_unit_not_allowed':'原单位不被允许',
 'invalid_decimal':'非有限数值',
 'value_out_of_range':'越界值',
 'precision_loss':'换算后超精度',
 'null_required':'必填值为空',
 'missing_column':'缺源字段',
 'text_too_long':'文本超长',
 'invalid_datetime':'时间格式无效',
 'duplicate_natural_key':'自然键重复',
 'invalid_row':'其他行级错误',
}
