import {fireEvent, render, screen} from "@testing-library/react";
import {describe, expect, it, vi} from "vitest";
import QaModal from "./QaModal.jsx";

const qa = {schema:{pass:true,n_pages:1,n_fail:0,n_review:1,elapsed_s:.1,gate:"INFER_SCHEMA",pages:[{page:13,pass:true,schema_mode:"lattice",confidence:.95,n_accept:1,n_review:1,n_reject:0,carry_used:false}]}};

describe("QaModal",()=>{
  it("keeps the modal mounted when a page is selected",()=>{
    const onPage=vi.fn(),onClose=vi.fn();
    render(<QaModal open qa={qa} run="sample" page={8} onPage={onPage} onClose={onClose} stage="schema" setStage={()=>{}}/>);
    fireEvent.click(screen.getByRole("button",{name:"p.13"}));
    expect(onPage).toHaveBeenCalledWith(13);
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByRole("heading",{name:"Run QA"})).toBeInTheDocument();
  });
  it("does not expose retired model stages",()=>{
    render(<QaModal open qa={qa} run="sample" page={13} onPage={()=>{}} onClose={()=>{}} stage="schema" setStage={()=>{}}/>);
    expect(screen.queryByRole("button",{name:/Archived Layout/})).not.toBeInTheDocument();
    expect(screen.queryByRole("button",{name:/Archived Cells/})).not.toBeInTheDocument();
  });
});
