* IDENTIFICATION DIVISION SAMPLE — AUTHOR / DATE-WRITTEN
* Regression fixture for the real production lexer + parser: AUTHOR and
* DATE-WRITTEN are not in the lexer's reserved-keyword set (only
* PROGRAM-ID is), so they are emitted as IDENTIFIER tokens rather than
* KEYWORD tokens. The parser must still recognise them as clause names
* at this grammar position. Deliberately has no ENVIRONMENT DIVISION
* (unimplemented, separate, pre-existing limitation) so this fixture
* isolates the identification-division fix on its own.
 IDENTIFICATION DIVISION.
 PROGRAM-ID. ACCTBATCH.
 AUTHOR. AI-MODERNIZATION-TEST.
 DATE-WRITTEN. 2026-09-02.
 DATA DIVISION.
 WORKING-STORAGE SECTION.
 01 WS-FLAG PIC X(01).
 PROCEDURE DIVISION.
 MAIN-PARA.
     STOP RUN.
