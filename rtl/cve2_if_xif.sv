/*
 Copyright 2021 TU Wien

 This file, and derivatives thereof are licensed under the
 Solderpad License, Version 2.0 (the "License");
 Use of this file means you agree to the terms and conditions
 of the license and are in full compliance with the License.
 You may obtain a copy of the License at

 https://solderpad.org/licenses/SHL-2.0/

 Unless required by applicable law or agreed to in writing, software
 and hardware implementations thereof
 distributed under the License is distributed on an "AS IS" BASIS,
 WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, EITHER EXPRESSED OR IMPLIED.
 See the License for the specific language governing permissions and
 limitations under the License.
 */

////////////////////////////////////////////////////////////////////////////////
// Engineer:       Michael Platzer - michael.platzer@tuwien.ac.at             //
//                                                                            //
// Additional contributions by:                                               //
//                 Abdullah Allam - abdulal@stud.ntnu.no                      //
//                                                                            //
// Design Name:    CORE-V XIF eXtension Interface                             //
// Project Name:   RI5CY                                                      //
// Language:       SystemVerilog                                              //
//                                                                            //
// Description:    Definition of the CORE-V XIF eXtension Interface.          //
//                                                                            //
////////////////////////////////////////////////////////////////////////////////

interface cve2_if_xif
#(
  parameter int unsigned X_NUM_RS               = 2,  // Number of register file read ports that can be used by the eXtension interface
  parameter int unsigned X_ID_WIDTH             = 4,  // Width of ID field.
  parameter int unsigned X_RFR_WIDTH            = 32, // Register file read access width for the eXtension interface
  parameter int unsigned X_RFW_WIDTH            = 32, // Register file write access width for the eXtension interface
  parameter int unsigned X_NUM_HARTS            = 1,  // Number of harts associated with the eXtension interface
  parameter int unsigned X_HARTID_WIDTH         = 1,  // Width of the hartid signals in the eXtension interface
  parameter int unsigned X_DUALREAD             = 0,  // Dual register file read
  parameter int unsigned X_DUALWRITE            = 0,  // Dual register file write
  parameter int unsigned X_ISSUE_REGISTER_SPLIT = 0,  // Does the interface pipeline register interface
  parameter logic [31:0] X_MISA                 = '0, // MISA extensions implemented on the eXtension interface
  parameter logic [ 1:0] X_ECS_XS               = '0  // Default value for mstatus.XS
);

  localparam int XLEN = 32;
  localparam int FLEN = 32;

  // Type Definitions
  typedef logic [X_NUM_RS+X_DUALREAD-1:0] readregflags_t; // Vector with a flag per possible source register. This depends upon the number of read ports and their ability to read register pairs. The bit positions map to registers as follows: Low indices correspond to low operand numbers, and the even part of the pair has the lower index than the odd one.

  typedef logic [X_DUALWRITE:0] writeregflags_t; // Bit vector indicating destination registers for write back. The width depends on the ability to perform dual write. If X_DUALWRITE = 0, this signal is a single bit. Bit 1 may only be set when bit 0 is also set. In this case, the vector indicates that a register pair is used.
  
  typedef logic [X_ID_WIDTH-1:0] id_t; // Identification of the offloaded instruction. See Identification for details on the identifiers 
  
  typedef logic [X_HARTID_WIDTH-1:0] hartid_t; // Identification of the hart offloading the instruction. Only relevant in multi-hart systems. Hart IDs are not required to to be numbered continuously. The hart ID would usually correspond to mhartid, but it is not required to do so.

  typedef struct packed {
    logic [31:0]  instr;  // Offloaded instruction
    id_t          id;     // Identification of the offloaded instruction
    hartid_t      hartid; // Identification of the hart offloading the instruction.
  } x_issue_req_t;

  typedef struct packed {
    logic           accept;         // Is the offloaded instruction (id) accepted by the coprocessor?
    writeregflags_t writeback;      // Will the coprocessor perform a writeback in the core to rd?
    readregflags_t  register_read;  // Will the coprocessor require specific registers to be read?
    logic           ecswrite ;      // Will the coprocessor write the Extension Context Status in mstatus?
  } x_issue_resp_t;

  typedef struct packed {
    id_t     id;           // Identification of the offloaded instruction
    hartid_t hartid;       // Identification of the hart offloading the instruction.
    logic    commit_kill;  // Shall an offloaded instruction be killed?
  } x_commit_t;

  typedef struct packed {
    hartid_t                               hartid;    // Identification of the hart offloading the instruction.
    id_t                                   id;        // Identification of the offloaded instruction. 
    logic [X_NUM_RS-1:0] [X_RFR_WIDTH-1:0] rs;        // Register file source operands for the offloaded instruction
    readregflags_t                         rs_valid;  // Validity of the register file source operand(s).
    logic [5:0]                            ecs;       // Extension Context Status ({mstatus.xs, mstatus.fs, mstatus.vs}).
    logic                                  ecs_valid; // Validity of the Extension Context Status.
  } x_register_t;

  typedef struct packed {
    id_t                         id;      // Identification of the offloaded instruction
    hartid_t                     hartid;  // Identification of the hart offloading the instruction.
    logic [X_RFW_WIDTH     -1:0] data;    // Register file write data value(s)
    logic [                 4:0] rd;      // Register file destination address(es)
    writeregflags_t              we;      // Register file write enable(s)
    logic [                 5:0] ecsdata; // Write data value for {mstatus.xs, mstatus.fs, mstatus.vs}
    logic [                 2:0] ecswe;   // Write enables for {mstatus.xs, mstatus.fs, mstatus.vs}
    logic                        exc;     // Did the instruction cause a synchronous exception?
    logic [                 5:0] exccode; // Exception code
    logic                        err;     // Did the instruction cause a bus error?
    logic                        dbg;     // Did the instruction cause a debug trigger match with ``mcontrol.timing`` = 0?
  } x_result_t;


  // Issue interface
  logic               issue_valid;
  logic               issue_ready;
  x_issue_req_t       issue_req;
  x_issue_resp_t      issue_resp;

  // Commit interface
  logic               commit_valid;
  x_commit_t          commit;

  // Register interface
  logic               register_valid;
  logic               register_ready;
  x_register_t        register;

  // Result interface
  logic               result_valid;
  logic               result_ready;
  x_result_t          result;

  // Port directions for host CPU
  modport cpu_issue (
    output issue_valid,
    input  issue_ready,
    output issue_req,
    input  issue_resp
  );
  modport cpu_commit (
    output commit_valid,
    output commit
  );
  modport cpu_register (
    output register_valid,
    input  register_ready,
    output register
  );
  modport cpu_result (
    input  result_valid,
    output result_ready,
    input  result
  );

  // Port directions for coprocessor
  modport coproc_issue (
    input  issue_valid,
    output issue_ready,
    input  issue_req,
    output issue_resp
  );
  modport coproc_commit (
    input  commit_valid,
    input  commit
  );
  modport coproc_register (
    input  register_valid,
    output register_ready,
    input  register
  );
  modport coproc_result (
    output result_valid,
    input  result_ready,
    output result
  );

endinterface : cve2_if_xif
