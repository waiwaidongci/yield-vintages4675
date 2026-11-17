export const pages=[['overview','业务总览'],['ingest','批次数据包'],['lots','批次修订台账'],['sources','业务底稿'],['policies','口径版本'],['recompute','重算与发布'],['runs','核算与复核'],['deliveries','定时交付'],['audit','过程留痕']];
export const currentPage=()=>location.hash.slice(1)||'overview';
