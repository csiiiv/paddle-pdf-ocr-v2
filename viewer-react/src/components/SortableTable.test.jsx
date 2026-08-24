import {fireEvent,render,screen,within} from "@testing-library/react";
import {describe,expect,it} from "vitest";
import SortableTable from "./SortableTable.jsx";

describe("SortableTable",()=>{
  it("sorts numeric cells ascending and descending",()=>{
    render(<SortableTable headers={["Page","Text"]} rows={[
      {page:10,text:"ten"},{page:2,text:"two"},{page:1,text:"one"},
    ]} cells={(row)=>[row.page,row.text]}/>);
    const values=()=>screen.getAllByRole("row").slice(1).map((row)=>within(row).getAllByRole("cell")[0].textContent);
    fireEvent.click(screen.getByRole("button",{name:/Page/}));
    expect(values()).toEqual(["1","2","10"]);
    fireEvent.click(screen.getByRole("button",{name:/Page/}));
    expect(values()).toEqual(["10","2","1"]);
  });
});
