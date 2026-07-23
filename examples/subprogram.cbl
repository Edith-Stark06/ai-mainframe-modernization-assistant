      *=======================================================*
      * subprogram.cbl                                        *
      * Purpose: Demonstrate CALL with USING arguments.       *
      *=======================================================*
       IDENTIFICATION DIVISION.
       PROGRAM-ID. SUBPROGRAM.

       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-INPUT  PIC 9(5) VALUE ZEROS.
       01 WS-OUTPUT PIC 9(6) VALUE ZEROS.

       PROCEDURE DIVISION.
       MAIN-PARA.
           MOVE 42 TO WS-INPUT.
           CALL "CALC-TOTAL" USING WS-INPUT WS-OUTPUT.
           DISPLAY WS-OUTPUT.
           STOP RUN.
