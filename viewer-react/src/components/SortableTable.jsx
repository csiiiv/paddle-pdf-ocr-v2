import {useMemo,useState} from "react";

function compareValues(left,right){
  const empty=(value)=>value===null||value===undefined||value==="";
  if(empty(left)||empty(right))return empty(left)===empty(right)?0:empty(left)?1:-1;
  if(typeof left==="number"&&typeof right==="number")return left-right;
  if(typeof left==="boolean"&&typeof right==="boolean")return Number(left)-Number(right);
  return String(left).localeCompare(String(right),undefined,{numeric:true,sensitivity:"base"});
}

export default function SortableTable({headers,rows,cells,rowKey,rowProps,renderCell,initialSort=null}){
  const [sort,setSort]=useState(()=>initialSort||{column:null,direction:1});
  const prepared=useMemo(()=>rows.map((item,index)=>({item,index,values:cells(item,index)})),[rows,cells]);
  const ordered=useMemo(()=>{
    if(sort.column===null)return prepared;
    return [...prepared].sort((a,b)=>sort.direction*compareValues(a.values[sort.column],b.values[sort.column])||a.index-b.index);
  },[prepared,sort]);
  const choose=(column)=>setSort((current)=>current.column===column
    ?{column,direction:-current.direction}:{column,direction:1});
  return <table><thead><tr>{headers.map((header,column)=>{
    const active=sort.column===column;
    return <th key={`${header}-${column}`} aria-sort={active?(sort.direction===1?"ascending":"descending"):"none"}>
      <button className="sort-header" type="button" onClick={()=>choose(column)}>{header}<span aria-hidden="true">{active?(sort.direction===1?" ▲":" ▼"):" ↕"}</span></button>
    </th>;
  })}</tr></thead><tbody>{ordered.map(({item,index,values})=><tr key={rowKey?.(item,index)??index} {...rowProps?.(item,index)}>{values.map((value,column)=><td key={column}>{renderCell?renderCell(value,column,item,index):value??"—"}</td>)}</tr>)}</tbody></table>;
}
