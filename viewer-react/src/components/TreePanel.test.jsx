import {cleanup,fireEvent,render,screen} from "@testing-library/react";
import {afterEach,describe,expect,it,vi} from "vitest";
import TreePanel from "./TreePanel.jsx";

afterEach(cleanup);

const tree={
  table:{table_id:"by-ou-001",title:"Appropriations by Operating Units"},
  roots:["root"],
  diagnostics:{n_nodes:4,n_pages:2,n_review_flags:1},
  nodes:[
    {id:"root",parent:null,kind:"table_root",label:"Appropriations by Operating Units",page:null,children:["section"],flags:[]},
    {id:"section",parent:"root",kind:"section",label:"A. REGULAR PROGRAMS",page:13,children:["region"],flags:[]},
    {id:"region",parent:"section",kind:"region",label:"Region I - Ilocos",page:13,row_section_id:14,children:["office"],flags:[]},
    {id:"office",parent:"region",kind:"office",label:"Ilocos Norte District Engineering Office",page:14,row_section_id:0,children:[],flags:["review"],
      amounts:{PS:{text:"12, 000, 000",role:"PS"},MOOE:{text:"5, 854, 000",role:"MOOE"},CO:{text:"30, 000, 000",role:"CO"},Total:{text:"47, 854, 000",role:"Total"}},
      total:{text:"47, 854, 000",role:"Total"}},
  ],
};

describe("TreePanel",()=>{
  it("selects only the clicked tree node, not its row-section layer",()=>{
    const onSelect=vi.fn();
    render(<TreePanel tree={tree} currentPage={14} selection={null} onSelect={onSelect}/>);
    expect(screen.getByText("Ilocos Norte District Engineering Office")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Ilocos Norte District Engineering Office"));
    expect(onSelect).toHaveBeenCalledWith("treeNode","office",expect.objectContaining({id:"office",__page:14}));
  });

  it("highlights only the selected tree node row",()=>{
    const selection={type:"treeNode",id:"region",item:{id:"region",__page:13}};
    const {container}=render(<TreePanel tree={tree} currentPage={13} selection={selection} onSelect={()=>{}}/>);
    expect(container.querySelector('tr[data-node-id="region"]')).toHaveClass("selected");
    expect(container.querySelector('tr[data-node-id="section"]')).not.toHaveClass("selected");
    expect(container.querySelector('tr[data-node-id="root"]')).not.toHaveClass("selected");
  });

  it("filters labels while retaining their ancestor path",()=>{
    render(<TreePanel tree={tree} currentPage={13} selection={null} onSelect={()=>{}}/>);
    fireEvent.change(screen.getByLabelText("Search tree"),{target:{value:"Ilocos Norte"}});
    expect(screen.getByText("Ilocos Norte District Engineering Office")).toBeInTheDocument();
    expect(screen.getByText("Region I - Ilocos")).toBeInTheDocument();
    expect(screen.getByText("A. REGULAR PROGRAMS")).toBeInTheDocument();
  });

  it("collapses the branches of an entry's immediate children",()=>{
    const onSelect=vi.fn();
    render(<TreePanel tree={tree} currentPage={14} selection={null} onSelect={onSelect}/>);
    expect(screen.getByText("Ilocos Norte District Engineering Office")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button",{name:"Collapse child branches of Appropriations by Operating Units"}));
    expect(screen.getByText("A. REGULAR PROGRAMS")).toBeInTheDocument();
    expect(screen.queryByText("Region I - Ilocos")).not.toBeInTheDocument();
    expect(screen.queryByText("Ilocos Norte District Engineering Office")).not.toBeInTheDocument();
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("shows a useful message when the tree artifact is absent",()=>{
    render(<TreePanel tree={null} currentPage={13} selection={null} onSelect={()=>{}}/>);
    expect(screen.getByText(/Run stage 002.30/)).toBeInTheDocument();
  });

  it("renders every amount column present in the tree",()=>{
    render(<TreePanel tree={tree} currentPage={14} selection={null} onSelect={()=>{}}/>);
    expect(screen.getByRole("columnheader",{name:"PS"})).toBeInTheDocument();
    expect(screen.getByRole("columnheader",{name:"MOOE"})).toBeInTheDocument();
    expect(screen.getByRole("columnheader",{name:"CO"})).toBeInTheDocument();
    expect(screen.getByRole("columnheader",{name:"Total"})).toBeInTheDocument();
    expect(screen.getByText("5, 854, 000")).toBeInTheDocument();
    expect(screen.getByText("47, 854, 000")).toBeInTheDocument();
  });

  it("identifies the PAP stage when its artifact is absent",()=>{
    render(<TreePanel tree={null} stage="002.40" currentPage={115} selection={null} onSelect={()=>{}}/>);
    expect(screen.getByText(/Run stage 002.40/)).toBeInTheDocument();
  });
});
