public class CombinedProgram {

    private int counter;

    public static void main(String[] args) {
        new CombinedProgram().run();
    }

    public void run() {

        if (counter > 0) {
            counter += 1;
        } else {
            counter = 0;
        }

    }

}
