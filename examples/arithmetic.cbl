      *=======================================================*
      * arithmetic.cbl                                        *
      * Purpose: Demonstrate arithmetic statements.           *
      *=======================================================*
       IDENTIFICATION DIVISION.
       PROGRAM-ID. ARITHMETIC.

       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-A     PIC 9(5) VALUE 100.
       01 WS-B     PIC 9(5) VALUE 50.
       01 WS-TOTAL PIC 9(6) VALUE ZEROS.
       01 WS-DIFF  PIC 9(5) VALUE ZEROS.

       PROCEDURE DIVISION.
       MAIN-PARA.
           MOVE 100 TO WS-A.
           MOVE 50  TO WS-B.
           ADD WS-A TO WS-TOTAL.
           ADD WS-B TO WS-TOTAL.
           SUBTRACT WS-B FROM WS-A.
           MULTIPLY WS-A BY WS-B.
           DIVIDE WS-B INTO WS-A.
           DISPLAY WS-TOTAL.
           STOP RUN.
