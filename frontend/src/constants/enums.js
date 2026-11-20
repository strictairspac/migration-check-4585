export const ROLES={admin:'管理员',operator:'操作员',viewer:'观察员'};
export const STATUSES={queued:'等待处理',running:'迁移中',completed:'已完成',failed:'失败',cancelled:'已取消'};
export const TYPES={sample_code:'text',test_name:'text',result_value:'decimal',unit:'text',measured_at:'datetime'};
export const REJECT_REASON_LABELS={
 unit_rule_missing:'缺少换算规则',
 source_unit_not_allowed:'原单位不被允许',
 invalid_decimal:'非有限数值',
 value_out_of_range:'越界值',
 precision_loss:'换算后超精度',
 null_required:'必填值为空',
 missing_column:'缺源字段',
 text_too_long:'文本超长',
 invalid_datetime:'时间格式无效',
 duplicate_natural_key:'自然键重复',
 invalid_row:'其他行级错误',
};
