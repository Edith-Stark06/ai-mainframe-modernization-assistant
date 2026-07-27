       IDENTIFICATION DIVISION.
       PROGRAM-ID. IF-ELSE-TEST.
       
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  AGE         PIC 9(2) VALUE 20.
       
       PROCEDURE DIVISION.
       MAIN-PARA.
           IF AGE > 18
               DISPLAY "ADULT"
           ELSE
               DISPLAY "MINOR"
           END-IF.
           STOP RUN.
