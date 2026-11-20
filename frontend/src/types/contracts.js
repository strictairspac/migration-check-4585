/** @typedef {{id:number,name:string,source_file:string,rows:object[]}} Batch */
/** @typedef {{test_name:string,target_unit:string,precision:number,allowed_units:string[],factors:Object<string,string>,min_value:string,max_value:string}} UnitRule */
/** @typedef {{id:number,name:string,batch_id:number,rules:object[],unit_rules:UnitRule[],chunk_size:number}} Mapping */
/** @typedef {{sample_code:string,test_name:string,result_value:string,unit:string,measured_at:string,original_value:string,original_unit:string}} TargetRow */
/** @typedef {{id:number,name:string,status:'queued'|'running'|'completed'|'failed'|'cancelled',result:object|null}} Run */
export {};
