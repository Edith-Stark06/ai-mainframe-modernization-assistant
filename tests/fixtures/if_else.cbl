       IDENTIFICATION DIVISION.
       PROGRAM-ID. IF-ELSE.
       
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-VAL PIC 9(2) VALUE 10.
       
       PROCEDURE DIVISION.
       MAIN-PARAGRAPH.
           IF WS-VAL > 5
               DISPLAY "GREATER"
           ELSE
               DISPLAY "LESS OR EQUAL"
           END-IF.
           STOP RUN.
