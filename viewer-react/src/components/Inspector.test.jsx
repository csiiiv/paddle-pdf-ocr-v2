import {cleanup,fireEvent,render,screen} from "@testing-library/react";
import {afterEach,describe,expect,it} from "vitest";
import Inspector from "./Inspector.jsx";

afterEach(cleanup);

const flag=(id,code)=>({
  flag_id:id,
  severity:"review",
  code,
  object_type:"row_section",
  object_id:id,
  message:`Message ${id}`,
  phrase_ids:[],
});

describe("Flags inspector",()=>{
  it("shows flags from every loaded page and highlights the current PDF page",()=>{
    const props={
      panel:"flags",
      layers:{sections:{flagged_objects:[flag(2,"CURRENT")]},geometry:{}},
      allLayers:[
        {page:14,sections:{flagged_objects:[flag(2,"CURRENT")]},geometry:{}},
        {page:13,sections:{flagged_objects:[flag(1,"EARLIER")]},geometry:{}},
      ],
      showAll:true,
      selection:null,
      onSelect:()=>{},
      flagFilter:{},
      onFlagFilter:()=>{},
      onShowAll:()=>{},
      flaggedPages:[13,14],
    };
    const {container,rerender}=render(<Inspector {...props} currentPage={14}/>);
    expect(screen.getByRole("columnheader",{name:"Page"})).toBeInTheDocument();
    expect(screen.getByRole("checkbox",{name:"All page data"})).toBeChecked();
    expect(screen.getByText("EARLIER")).toBeInTheDocument();
    expect(screen.getByText("CURRENT")).toBeInTheDocument();
    const rows=[...container.querySelectorAll("tbody tr")];
    expect(rows).toHaveLength(2);
    expect(rows[0].querySelector("td")).toHaveTextContent("13");
    expect(rows[0]).not.toHaveClass("current-page");
    expect(rows[1]).toHaveClass("current-page");
    expect(document.activeElement).toBe(rows[1]);
    fireEvent.click(screen.getByRole("button",{name:/Page/}));
    const descending=[...container.querySelectorAll("tbody tr")];
    expect(descending[0].querySelector("td")).toHaveTextContent("14");
    expect(screen.getByRole("columnheader",{name:"Page"})).toHaveAttribute("aria-sort","descending");
    rerender(<Inspector {...props} currentPage={13}/>);
    const page13=container.querySelector('tr[data-type="flag"][data-page="13"]');
    expect(page13).toHaveClass("current-page");
    expect(document.activeElement).toBe(page13);
  });
});
