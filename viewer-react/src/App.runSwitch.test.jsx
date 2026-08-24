import App from "./App.jsx";
import {cleanup,fireEvent,render,screen,waitFor} from "@testing-library/react";
import {afterEach,beforeEach,describe,expect,it,vi} from "vitest";

vi.mock("./components/PdfPane.jsx",()=>({default:()=>null}));

afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.restoreAllMocks()});

function jsonResponse(body,ok=true){
  return Promise.resolve({ok,status:ok?200:404,json:async()=>body,text:async()=>JSON.stringify(body)});
}

describe("run dropdown dataset switching",()=>{
  beforeEach(()=>{
    window.history.replaceState(null,"","/?run=HFEP&page=13&panel=tree");
    const hfepViewer={run:"HFEP",pdf:"pdfs/HFEP.pdf",pages:[1,13]};
    const nepViewer={run:"NEP-2027-VOLUME-2B_OCR",pdf:"pdfs/NEP-2027-VOLUME-2B_OCR.pdf",pages:[1,13,115]};
    const hfepTree={table:{title:"HFEP Medical"},roots:["root"],diagnostics:{n_nodes:1,n_pages:1,n_review_flags:0},nodes:[{id:"root",parent:null,kind:"table_root",label:"HFEP Medical",page:null,children:[],flags:[]}]};
    const nepTree={table:{title:"NEP Appropriations"},roots:["root"],diagnostics:{n_nodes:1,n_pages:1,n_review_flags:0},nodes:[{id:"root",parent:null,kind:"table_root",label:"NEP Appropriations",page:null,children:[],flags:[]}]};
    vi.stubGlobal("fetch",vi.fn(async(input)=>{
      const url=String(input);
      if(url.includes("/api/runs"))return jsonResponse(["HFEP","NEP-2027-VOLUME-2B_OCR"]);
      if(url.includes("/api/flag-index"))return jsonResponse({pages:[]});
      if(url.includes("output/HFEP/viewer.json"))return jsonResponse(hfepViewer);
      if(url.includes("output/NEP-2027-VOLUME-2B_OCR/viewer.json"))return jsonResponse(nepViewer);
      if(url.includes("output/HFEP/002.30-by-ou-tree/tree.json"))return jsonResponse(hfepTree);
      if(url.includes("output/NEP-2027-VOLUME-2B_OCR/002.30-by-ou-tree/tree.json"))return jsonResponse(nepTree);
      if(url.includes("fixtures/by_ou_table_seeds.json"))return jsonResponse({tables:[]});
      if(url.endsWith(".json"))return jsonResponse({},false);
      return jsonResponse({},false);
    }));
  });

  it("switches tree dataset when the run dropdown changes",async()=>{
    render(<App/>);
    await waitFor(()=>expect(screen.getAllByText("HFEP Medical").length).toBeGreaterThan(0));
    fireEvent.change(screen.getByLabelText("Dataset run"),{target:{value:"NEP-2027-VOLUME-2B_OCR"}});
    await waitFor(()=>expect(screen.getAllByText("NEP Appropriations").length).toBeGreaterThan(0));
    expect(screen.queryByText("HFEP Medical")).not.toBeInTheDocument();
    expect(new URLSearchParams(location.search).get("run")).toBe("NEP-2027-VOLUME-2B_OCR");
  });
});
