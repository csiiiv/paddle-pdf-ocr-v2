import {fireEvent, render, screen} from "@testing-library/react";
import {describe, expect, it, vi} from "vitest";
import QaModal from "./QaModal.jsx";

const qa = {sections:{pass:true,n_pages:1,n_fail:0,elapsed_s:.1,gate:"TABLE_GEOMETRIC_SECTIONS",pages:[{page:13,pass:true,n_header_sections:3,n_column_sections:5,n_alignment_boundaries:20,n_row_sections:21,n_cell_sections:105,n_nonempty_cell_sections:84,n_findings:0}]}};

describe("QaModal",()=>{
  it("keeps the modal mounted when a page is selected",()=>{
    const onPage=vi.fn(),onClose=vi.fn();
    render(<QaModal open qa={qa} run="sample" page={8} onPage={onPage} onClose={onClose} stage="sections" setStage={()=>{}}/>);
    fireEvent.click(screen.getByRole("button",{name:"p.13"}));
    expect(onPage).toHaveBeenCalledWith(13);
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByRole("heading",{name:"Run QA"})).toBeInTheDocument();
  });
  it("does not expose retired model stages",()=>{
    render(<QaModal open qa={qa} run="sample" page={13} onPage={()=>{}} onClose={()=>{}} stage="sections" setStage={()=>{}}/>);
    expect(screen.queryByRole("button",{name:/Archived Layout/})).not.toBeInTheDocument();
    expect(screen.queryByRole("button",{name:/Archived Cells/})).not.toBeInTheDocument();
  });
});
